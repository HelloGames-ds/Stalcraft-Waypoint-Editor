from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

from PIL import Image

if getattr(sys, "frozen", False):
    ROOT_DIR = Path(sys.executable).resolve().parent
else:
    ROOT_DIR = Path(__file__).resolve().parent
PDA_DIR = ROOT_DIR / "pda"
SCFILE_DIR = ROOT_DIR / "sc-file-master"
CACHE_DIR = ROOT_DIR / ".cache" / "tiles"
WAYPOINT_ICONS_CACHE_DIR = ROOT_DIR / ".cache" / "waypoint_icons"
WAYPOINT_ICONS_STATIC_DIR = ROOT_DIR / "assets" / "waypoint_icons"
WAYPOINTS_PATH = ROOT_DIR / "waypoints.cfg"
APP_CONFIG_PATH = ROOT_DIR / "app_config.json"
WAYPOINT_ICONS_OL_PATH = ROOT_DIR / "atlas_map_waypoint.ol"
WAYPOINT_ATLAS_JSON_PATH = ROOT_DIR / "atlas_map_waypoint.sheet.json"

TILE_PATTERN = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.(ol|mic)$")
WAYPOINT_ICON_FRAME_KEYS: list[str] = [
    "waypoint_player_custom",
    "waypoint_player_custom_chest",
    "waypoint_player_custom_cross",
    "waypoint_player_custom_flag",
    "waypoint_player_custom_flash",
    "waypoint_player_custom_magnifier",
    "waypoint_player_custom_question",
]
WAYPOINT_ICON_NAMES: dict[int, str] = {
    0: "custom",
    1: "chest",
    2: "cross",
    3: "flag",
    4: "flash",
    5: "magnifier",
    6: "question",
}
WAYPOINT_ICON_BBOXES_FALLBACK: dict[int, tuple[int, int, int, int]] = {
    0: (130, 168, 149, 192),
    1: (127, 127, 153, 152),
    2: (135, 408, 146, 418),
    3: (129, 458, 149, 472),
    4: (137, 288, 146, 300),
    5: (135, 328, 144, 342),
    6: (136, 368, 144, 376),
}


@dataclass(frozen=True)
class TileInfo:
    x: int
    z: int
    extension: str
    path: Path


@dataclass(frozen=True)
class ZoneImageInfo:
    name: str
    png_path: Path
    min_tx: int
    max_tx: int
    min_tz: int
    max_tz: int
    image_width: int
    image_height: int
    tiles_wide: int
    tiles_high: int


@dataclass
class MapInfo:
    map_id: str
    name: str
    path: Path
    extension: str
    tiles: Dict[tuple[int, int], TileInfo]
    zones: list[ZoneImageInfo]
    min_x: int
    max_x: int
    min_z: int
    max_z: int
    map_type: str = "tiles"

    def to_public(self) -> dict:
        return {
            "id": self.map_id,
            "name": self.name,
            "tileCount": len(self.tiles),
            "zoneCount": len(self.zones),
            "extension": self.extension,
            "mapType": self.map_type,
            "bounds": {
                "minX": self.min_x,
                "maxX": self.max_x,
                "minZ": self.min_z,
                "maxZ": self.max_z,
            },
            "size": {
                "tilesX": self.max_x - self.min_x + 1,
                "tilesZ": self.max_z - self.min_z + 1,
            },
        }


class SimpleMapperCore:
    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = (root_dir or ROOT_DIR).resolve()
        self.pda_dir = self.root_dir / "pda"
        self.cache_dir = self.root_dir / ".cache" / "tiles"
        self.waypoint_icons_cache_dir = self.root_dir / ".cache" / "waypoint_icons"
        self.waypoint_icons_static_dir = self.root_dir / "assets" / "waypoint_icons"
        self.backups_dir = self.root_dir / "backups" / "waypoints"
        self.app_config_path = self.root_dir / "app_config.json"
        self.app_config = self.load_app_config()
        self.waypoints_path = self.discover_waypoints_path()
        self.waypoint_icons_ol_path = self.root_dir / "atlas_map_waypoint.ol"
        self.waypoint_atlas_json_path = self.root_dir / "atlas_map_waypoint.sheet.json"
        self._maps_cache: Dict[str, MapInfo] | None = None
        self._waypoint_icon_bboxes_cache: dict[int, tuple[int, int, int, int]] | None = None
        self._startup_backup_done = False

    def load_app_config(self) -> dict:
        defaults = {"exbo_dir": "", "language": "ru", "language_initialized": False}
        if not self.app_config_path.exists():
            return defaults
        try:
            loaded = json.loads(self.app_config_path.read_text(encoding="utf-8"))
        except Exception:
            return defaults
        if not isinstance(loaded, dict):
            return defaults
        result = dict(defaults)
        exbo_dir = str(loaded.get("exbo_dir", "")).strip()
        result["exbo_dir"] = exbo_dir
        language = str(loaded.get("language", "ru")).strip().lower()
        result["language"] = language if language in {"ru", "en"} else "ru"
        result["language_initialized"] = bool(loaded.get("language_initialized", False))
        return result

    def save_app_config(self) -> None:
        self.app_config_path.write_text(
            json.dumps(self.app_config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def requires_language_setup(self) -> bool:
        return not bool(self.app_config.get("language_initialized", False))

    def get_language(self) -> str:
        language = str(self.app_config.get("language", "ru")).strip().lower()
        return language if language in {"ru", "en"} else "ru"

    def set_language(self, language: str) -> str:
        normalized = str(language).strip().lower()
        if normalized not in {"ru", "en"}:
            normalized = "ru"
        self.app_config["language"] = normalized
        self.app_config["language_initialized"] = True
        self.save_app_config()
        return normalized

    def get_default_exbo_dir(self) -> Path:
        return Path.home() / "AppData" / "Roaming" / "EXBO"

    def get_configured_exbo_dir(self) -> Path | None:
        raw_value = str(self.app_config.get("exbo_dir", "")).strip()
        if not raw_value:
            return None
        candidate = Path(raw_value)
        if not candidate.is_absolute():
            candidate = (self.root_dir / candidate).resolve()
        return candidate

    def requires_exbo_setup(self) -> bool:
        configured = self.get_configured_exbo_dir()
        return configured is None or not configured.exists() or not configured.is_dir()

    def get_exbo_dir(self) -> Path:
        configured = self.get_configured_exbo_dir()
        if configured is not None:
            return configured
        return self.get_default_exbo_dir()

    def build_waypoints_path_from_exbo_dir(self, exbo_dir: Path) -> Path:
        return exbo_dir / "runtime" / "stalcraft" / "config" / "waypoints.cfg"

    def set_exbo_dir(self, path_str: str) -> Path:
        candidate = Path(path_str.strip().strip('"'))
        if not candidate.is_absolute():
            candidate = (self.root_dir / candidate).resolve()
        if not candidate.exists() or not candidate.is_dir():
            raise FileNotFoundError("EXBO folder not found")
        self.app_config["exbo_dir"] = str(candidate)
        self.save_app_config()
        self.waypoints_path = self.build_waypoints_path_from_exbo_dir(candidate)
        return candidate

    def discover_waypoints_path(self) -> Path:
        candidates = [
            self.build_waypoints_path_from_exbo_dir(self.get_exbo_dir()),
            self.root_dir / "waypoints.cfg",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return candidates[0]

    def backup_waypoints_file(self, path: Path) -> Path | None:
        if not path.exists() or not path.is_file():
            return None
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backups_dir / f"{path.stem}_{stamp}{path.suffix}"
        shutil.copy2(path, backup_path)
        return backup_path

    def ensure_startup_waypoints_backup(self) -> Path | None:
        if self._startup_backup_done:
            return None
        self._startup_backup_done = True
        return self.backup_waypoints_file(self.get_waypoints_path())

    def get_scfile_formats(self):
        scfile_dir = (self.root_dir / "sc-file-master").resolve()
        if str(scfile_dir) not in sys.path:
            sys.path.insert(0, str(scfile_dir))
        from scfile import formats  # type: ignore

        return formats

    def scan_zone_png_maps(self) -> Dict[str, MapInfo]:
        maps: Dict[str, MapInfo] = {}
        search_roots = [
            self.root_dir / "assets" / "maps",
            self.root_dir / "zone_exports",
        ]

        for exports_dir in search_roots:
            if not exports_dir.exists():
                continue

            for folder in sorted(exports_dir.iterdir()):
                if not folder.is_dir():
                    continue

                manifest_path = folder / "zone_manifest.json"
                if not manifest_path.exists():
                    continue

                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue

                if manifest.get("export_type") != "zone_pngs":
                    continue

                zones_raw = manifest.get("zones") or []
                if not isinstance(zones_raw, list) or not zones_raw:
                    continue

                zones: list[ZoneImageInfo] = []
                xs: list[int] = []
                zs: list[int] = []
                for index, item in enumerate(zones_raw):
                    try:
                        png_file = str(item["png_file"])
                        min_tx = int(item["min_tx"])
                        max_tx = int(item["max_tx"])
                        min_tz = int(item["min_tz"])
                        max_tz = int(item["max_tz"])
                    except (KeyError, TypeError, ValueError):
                        continue

                    png_path = folder / "zones_png" / png_file
                    if not png_path.exists():
                        continue

                    tiles_wide = int(item.get("tiles_wide", max_tx - min_tx + 1))
                    tiles_high = int(item.get("tiles_high", max_tz - min_tz + 1))
                    image_width = int(item.get("image_width", 0))
                    image_height = int(item.get("image_height", 0))
                    if image_width <= 0 or image_height <= 0:
                        with Image.open(png_path) as image:
                            image_width = image.width
                            image_height = image.height

                    zones.append(
                        ZoneImageInfo(
                            name=str(item.get("name") or f"zone_{index + 1}"),
                            png_path=png_path,
                            min_tx=min_tx,
                            max_tx=max_tx,
                            min_tz=min_tz,
                            max_tz=max_tz,
                            image_width=image_width,
                            image_height=image_height,
                            tiles_wide=tiles_wide,
                            tiles_high=tiles_high,
                        )
                    )
                    xs.extend([min_tx, max_tx])
                    zs.extend([min_tz, max_tz])

                if not zones:
                    continue

                map_id = str(manifest.get("export_pack") or folder.name)
                if map_id in maps:
                    continue
                maps[map_id] = MapInfo(
                    map_id=map_id,
                    name=str(manifest.get("source_map_name") or map_id),
                    path=folder,
                    extension="png",
                    tiles={},
                    zones=zones,
                    min_x=min(xs),
                    max_x=max(xs),
                    min_z=min(zs),
                    max_z=max(zs),
                    map_type="zone_pngs",
                )

        return maps

    def load_waypoint_icon_bboxes_from_json(self) -> dict[int, tuple[int, int, int, int]]:
        if not self.waypoint_atlas_json_path.exists():
            return {}

        try:
            data = json.loads(self.waypoint_atlas_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

        frames = data.get("frames", {})
        if not isinstance(frames, dict):
            return {}

        result: dict[int, tuple[int, int, int, int]] = {}
        for index, frame_key in enumerate(WAYPOINT_ICON_FRAME_KEYS):
            frame_data = frames.get(frame_key, {})
            rect = frame_data.get("frame", {})
            if not isinstance(rect, dict):
                continue
            try:
                x = int(rect["x"])
                y = int(rect["y"])
                w = int(rect["w"])
                h = int(rect["h"])
            except (KeyError, TypeError, ValueError):
                continue
            result[index] = (x, y, x + w - 1, y + h - 1)

        return result

    def get_waypoint_icon_bboxes(self) -> dict[int, tuple[int, int, int, int]]:
        if self._waypoint_icon_bboxes_cache is None:
            parsed = self.load_waypoint_icon_bboxes_from_json()
            merged = dict(WAYPOINT_ICON_BBOXES_FALLBACK)
            merged.update(parsed)
            self._waypoint_icon_bboxes_cache = merged
        return self._waypoint_icon_bboxes_cache

    def ensure_map_icons_atlas_png(self) -> Path:
        atlas_png = self.waypoint_icons_cache_dir / "map_icons_atlas.png"
        if atlas_png.exists():
            return atlas_png

        if not self.waypoint_icons_ol_path.exists():
            raise FileNotFoundError("map_icons.ol not found")

        self.waypoint_icons_cache_dir.mkdir(parents=True, exist_ok=True)
        formats = self.get_scfile_formats()

        with tempfile.TemporaryDirectory() as temp_dir:
            dds_path = Path(temp_dir) / "map_icons.dds"
            with formats.ol.OlDecoder(self.waypoint_icons_ol_path) as ol:
                with ol.to_dds() as dds:
                    dds.save(dds_path)
            with Image.open(dds_path) as image:
                image.convert("RGBA").save(atlas_png, format="PNG", optimize=True)

        return atlas_png

    def ensure_waypoint_icon_png(self, icon_index: int) -> Path:
        bbox = self.get_waypoint_icon_bboxes().get(icon_index)
        if bbox is None:
            raise KeyError(f"Unsupported icon index {icon_index}")

        static_icon_png = self.waypoint_icons_static_dir / f"{icon_index}.png"
        if static_icon_png.exists():
            return static_icon_png

        self.waypoint_icons_cache_dir.mkdir(parents=True, exist_ok=True)
        icon_png = self.waypoint_icons_cache_dir / f"{icon_index}.png"
        if icon_png.exists():
            return icon_png

        atlas_png = self.ensure_map_icons_atlas_png()
        with Image.open(atlas_png) as atlas:
            x1, y1, x2, y2 = bbox
            if x2 >= atlas.width or y2 >= atlas.height or x1 < 0 or y1 < 0:
                fallback = WAYPOINT_ICON_BBOXES_FALLBACK.get(icon_index)
                if fallback is None:
                    raise ValueError(f"Icon bbox out of atlas bounds for {icon_index}")
                x1, y1, x2, y2 = fallback
            cropped = atlas.crop((x1, y1, x2 + 1, y2 + 1))
            alpha = cropped.split()[-1]
            non_empty = alpha.getbbox() is not None
            alpha_pixels = sum(1 for value in alpha.getdata() if value > 0)
            if (not non_empty or alpha_pixels < 40) and icon_index in WAYPOINT_ICON_BBOXES_FALLBACK:
                fx1, fy1, fx2, fy2 = WAYPOINT_ICON_BBOXES_FALLBACK[icon_index]
                cropped = atlas.crop((fx1, fy1, fx2 + 1, fy2 + 1))

            cropped.save(icon_png, format="PNG", optimize=True)

        return icon_png

    def scan_maps(self) -> Dict[str, MapInfo]:
        zone_maps = self.scan_zone_png_maps()
        if zone_maps:
            return zone_maps

        maps: Dict[str, MapInfo] = {}

        if not self.pda_dir.exists():
            return maps

        for folder in sorted(self.pda_dir.iterdir()):
            if not folder.is_dir():
                continue

            tiles: Dict[tuple[int, int], TileInfo] = {}
            extension: str | None = None

            for file in folder.iterdir():
                if not file.is_file():
                    continue

                match = TILE_PATTERN.match(file.name)
                if not match:
                    continue

                x = int(match.group(1))
                z = int(match.group(2))
                ext = match.group(3)
                tiles[(x, z)] = TileInfo(x=x, z=z, extension=ext, path=file)
                extension = extension or ext

            if not tiles:
                continue

            xs = [tile.x for tile in tiles.values()]
            zs = [tile.z for tile in tiles.values()]
            map_id = folder.name

            maps[map_id] = MapInfo(
                map_id=map_id,
                name=folder.name,
                path=folder,
                extension=extension or "ol",
                tiles=tiles,
                zones=[],
                min_x=min(xs),
                max_x=max(xs),
                min_z=min(zs),
                max_z=max(zs),
                map_type="tiles",
            )

        return maps

    def get_maps(self, reload: bool = False) -> Dict[str, MapInfo]:
        if reload or self._maps_cache is None:
            self._maps_cache = self.scan_maps()
        return self._maps_cache

    def get_map(self, map_id: str, reload: bool = False) -> MapInfo:
        maps = self.get_maps(reload=reload)
        map_info = maps.get(map_id)
        if map_info is None:
            raise KeyError(f"Map '{map_id}' not found")
        return map_info

    def get_waypoints_path(self) -> Path:
        return self.waypoints_path

    def set_waypoints_path(self, path_str: str) -> Path:
        candidate = Path(path_str.strip().strip('"'))
        if not candidate.is_absolute():
            candidate = (self.root_dir / candidate).resolve()
        if not candidate.exists() or not candidate.is_file():
            raise FileNotFoundError("CFG file not found")
        self.waypoints_path = candidate
        return self.waypoints_path

    def load_raw_waypoints(self, path: Path | None = None) -> list[dict]:
        cfg_path = path or self.get_waypoints_path()
        if not cfg_path.exists():
            return []
        self.ensure_startup_waypoints_backup()

        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

        if not isinstance(raw, list):
            return []

        result: list[dict] = []
        for item in raw:
            if isinstance(item, dict):
                result.append(item)
        return result

    def parse_waypoints_data(self, raw_items: Iterable[dict]) -> List[dict]:
        result: List[dict] = []
        for index, item in enumerate(raw_items):
            pos = item.get("pos", {})
            if not isinstance(pos, dict):
                continue

            try:
                x = float(pos.get("x", 0.0))
                y = float(pos.get("y", 0.0))
                z = float(pos.get("z", 0.0))
            except (TypeError, ValueError):
                continue

            color_raw = int(item.get("color", -1))
            argb = color_raw & 0xFFFFFFFF
            color = {
                "argb": argb,
                "a": (argb >> 24) & 0xFF,
                "r": (argb >> 16) & 0xFF,
                "g": (argb >> 8) & 0xFF,
                "b": argb & 0xFF,
                "hex": f"#{(argb >> 16) & 0xFF:02X}{(argb >> 8) & 0xFF:02X}{argb & 0xFF:02X}",
            }
            icon_index = int(item.get("icon_index", 0))

            result.append(
                {
                    "id": index,
                    "name": item.get("name") or f"WP-{index + 1}",
                    "iconIndex": icon_index,
                    "iconName": WAYPOINT_ICON_NAMES.get(icon_index, "unknown"),
                    "colorRaw": color_raw,
                    "color": color,
                    "type": item.get("type", "manual"),
                    "pos": {"x": x, "y": y, "z": z},
                }
            )

        return result

    def parse_waypoints(self, path: Path | None = None) -> List[dict]:
        return self.parse_waypoints_data(self.load_raw_waypoints(path=path))

    def save_waypoints(self, payload: list[dict], path: Path | None = None) -> Path:
        target = path or self.get_waypoints_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        self.backup_waypoints_file(target)
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        target.write_text(text, encoding="utf-8")
        return target

    def ensure_cached_png(self, map_info: MapInfo, tile: TileInfo) -> Path:
        cache_dir = self.cache_dir / map_info.map_id
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_png = cache_dir / f"{tile.x}.{tile.z}.png"

        if cache_png.exists():
            return cache_png

        formats = self.get_scfile_formats()

        if tile.extension == "mic":
            with formats.mic.MicDecoder(tile.path) as mic:
                with mic.to_png() as png:
                    png.save(cache_png)
            return cache_png

        if tile.extension != "ol":
            raise ValueError(f"Unsupported tile extension '{tile.extension}'")

        with tempfile.TemporaryDirectory() as temp_dir:
            dds_path = Path(temp_dir) / "tile.dds"
            with formats.ol.OlDecoder(tile.path) as ol:
                with ol.to_dds() as dds:
                    dds.save(dds_path)

            with Image.open(dds_path) as image:
                image.convert("RGBA").save(cache_png, format="PNG", optimize=True)

        return cache_png

    def get_tile_png(self, map_id: str, x: int, z: int) -> Path:
        map_info = self.get_map(map_id)
        tile = map_info.tiles.get((x, z))
        if tile is None:
            raise KeyError(f"Tile '{x},{z}' not found")
        return self.ensure_cached_png(map_info, tile)

    def delete_tiles(self, map_id: str, coords: Iterable[tuple[int, int]]) -> dict:
        map_info = self.get_map(map_id)
        requested = {tuple(coord) for coord in coords}
        deleted = 0
        missing = 0
        failed: list[dict] = []

        for x, z in sorted(requested):
            tile = map_info.tiles.get((x, z))
            if tile is None:
                missing += 1
                continue

            try:
                tile.path.unlink(missing_ok=True)
                cache_png = self.cache_dir / map_info.map_id / f"{x}.{z}.png"
                cache_png.unlink(missing_ok=True)
                deleted += 1
            except OSError as exc:
                failed.append({"x": x, "z": z, "error": str(exc)})

        self.get_maps(reload=True)

        return {
            "ok": True,
            "mapId": map_id,
            "requested": len(requested),
            "deleted": deleted,
            "missing": missing,
            "failed": failed,
        }


core = SimpleMapperCore()
