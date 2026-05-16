from __future__ import annotations

import copy
import math
import sys
from collections import deque
from pathlib import Path

import dearpygui.dearpygui as dpg
import numpy as np
from PIL import Image

# Импорт для работы с Windows API
import ctypes
from ctypes import wintypes
import winreg

from app_constants import PROJECT_ROOT, RESOURCE_ROOT

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app_constants import (
    DEFAULT_MAP_ZOOM_MULTIPLIER,
    DEFAULT_MARKER_ZOOM_MULTIPLIER,
    INITIAL_ZOOM,
    INTERACTION_GRACE_FRAMES,
    INTERACTION_POINT_BUDGET,
    MARKER_TILE_MARGIN,
    MAX_MARKERS_ON_SCREEN,
    MAX_TILE_TEXTURES,
    MAX_VISIBLE_ICON_MARKERS,
    MAX_VISIBLE_POINT_MARKERS,
    MAX_WAYPOINT_LIST_ITEMS,
    POINT_OVERLAY_DOWNSCALE,
    POINT_OVERLAY_DOWNSCALE_HEAVY,
    SELECTION_CLICK_TOLERANCE_SCREEN_PX,
    SQUARE_RENDER_THRESHOLD,
    TILE_KEEP_EXTRA_MARGIN,
    UNDO_HISTORY_LIMIT,
    VISIBLE_TILE_MARGIN,
    WAYPOINT_HIDE_NAMES_SCALE,
    WAYPOINT_ICON_SCALE_SWITCH,
)
from app_types import TextureInfo
from image_mixin import ImageGenerationMixin
from i18n import translate
from layers_mixin import LayerEditorMixin
from ui_mixin import UIBuildMixin
from zone_mixin import ZoneLoadingMixin

from simplemapper_core import SimpleMapperCore, WAYPOINT_ICON_NAMES


class SimpleMapperDesktopApp(
    UIBuildMixin,
    ImageGenerationMixin,
    LayerEditorMixin,
    ZoneLoadingMixin,
):
    def __init__(self) -> None:
        self.core = SimpleMapperCore(PROJECT_ROOT, RESOURCE_ROOT)
        self.language_setup_required = self.core.requires_language_setup()
        self.language = "en" if self.language_setup_required else self.core.get_language()
        self.ui_config = self.load_ui_config()
        self.settings_config = self.load_settings_config()
        self.active_map_id: str | None = None
        self.active_map = None
        self.tile_size = 512
        self.tile_queue = deque()
        self.tile_textures: dict[tuple[int, int], TextureInfo] = {}
        self.tile_texture_tags: list[str] = []
        self.tile_last_used: dict[tuple[int, int], int] = {}
        self.frame_index = 0
        self.visible_tile_targets: set[tuple[int, int]] = set()
        self.cached_tile_targets: set[tuple[int, int]] = set()
        self.icon_textures: dict[int, TextureInfo] = {}
        self.raw_waypoints: list[dict] = []
        self.generated_raw_waypoints: list[dict] = []
        self.display_waypoints: list[dict] = []
        self.waypoint_chunks: dict[tuple[int, int], list[dict]] = {}
        self.last_visible_waypoint_count = 0
        self.last_waypoint_render_mode = "icons"
        self.overlay_texture_tag = "waypoint_overlay_texture"
        self.overlay_cache_key: tuple | None = None
        self.overlay_selected_screen: tuple[float, float] | None = None
        self.image_path: str = ""
        self.selected_waypoint_id: int | None = None
        self.map_zoom_multiplier = float(self.settings_config.get("map_zoom_multiplier", DEFAULT_MAP_ZOOM_MULTIPLIER))
        self.marker_zoom_multiplier = float(self.settings_config.get("marker_zoom_multiplier", DEFAULT_MARKER_ZOOM_MULTIPLIER))
        self.scale = self.clamp_map_scale(INITIAL_ZOOM * self.map_zoom_multiplier)
        self.camera_x = 0.0
        self.camera_y = 0.0
        self.tile_margin_chunks = VISIBLE_TILE_MARGIN
        self.marker_margin_chunks = MARKER_TILE_MARGIN
        self.max_markers_on_screen = int(self.settings_config["max_markers_on_screen"])
        self.square_render_threshold = int(self.settings_config["square_render_threshold"])
        self.max_tile_textures = MAX_TILE_TEXTURES
        self.effective_tile_cache_limit = self.max_tile_textures
        self.pending_fit = False
        self.needs_redraw = True
        self.last_viewer_size = (0, 0)
        self.interaction_active_until_frame = 0
        self.right_dragging = False
        self.right_drag_last = (0.0, 0.0)
        self.left_pressed = False
        self.left_pressed_in_viewer = False
        self.left_press_pos = (0.0, 0.0)
        self.dragging_waypoint_id: int | None = None
        self.show_waypoint_list = False
        self.selected_waypoint_ids: set[int] = set()
        self.selection_box_active = False
        self.selection_box_append = False
        self.selection_box_start_map = (0.0, 0.0)
        self.selection_box_current_map = (0.0, 0.0)
        self.selection_drag_active = False
        self.selection_drag_start_map = (0.0, 0.0)
        self.selection_drag_snapshot: list[dict] = []
        self.image_preview_texture_tag = "image_preview_texture"
        self.image_preview_bounds_map: tuple[float, float, float, float] | None = None
        self.image_preview_source_size = (0, 0)
        self.image_preview_texture_size = (0, 0)
        self.image_preview_selected = False
        self.image_preview_drag_mode: str | None = None
        self.image_preview_drag_start_map = (0.0, 0.0)
        self.image_preview_drag_initial_bounds: tuple[float, float, float, float] | None = None
        self.image_preview_marker_cache_key: tuple | None = None
        self.image_preview_marker_cache_points: list[tuple[int, int, int, int, int]] = []
        self.image_preview_marker_cache_size = (0, 0)
        self.image_preview_marker_cache_dirty = False
        self.enabled_zone_names: set[str] = set()
        self.zone_reload_pending = False
        self.zone_reveal_progress: dict[tuple[int, int], float] = {}
        self.zone_reveal_direction: dict[tuple[int, int], int] = {}
        self.zone_disable_pending: set[tuple[int, int]] = set()
        self.undo_stack: list[dict] = []
        self.redo_stack: list[dict] = []
        self.marker_layers: dict[str, set[tuple[str, int]]] = {}
        self.layer_visibility: dict[str, bool] = {}
        self.layer_counter = 1
        self.image_parser_mode = "fill"
        self.ui_theme_tag = "runtime_ui_theme"
        self.ui_subsection_theme_tag = "runtime_ui_subsection_theme"
        self.ui_subsection_header_theme_tag = "runtime_ui_subsection_header_theme"
        self.sidebar_visible = True
        self.sidebar_resize_active = False
        self.exbo_setup_required = self.core.requires_exbo_setup()
        self.pending_exbo_setup_modal = False
        self.selected_waypoint_name_mixed = False

    def t(self, key: str, **kwargs) -> str:
        return translate(self.language, key, **kwargs)

    def get_zone_translation_key(self, zone_name: str) -> str:
        normalized = (
            str(zone_name)
            .strip()
            .lower()
            .replace("+", " ")
            .replace("-", "_")
            .replace("/", "_")
        )
        normalized = "_".join(part for part in normalized.replace("__", "_").split())
        normalized = normalized.replace("norh", "north")
        return f"zone_{normalized}"

    def get_zone_display_name(self, zone_name: str) -> str:
        key = self.get_zone_translation_key(zone_name)
        translated = translate(self.language, key)
        return translated if translated != key else str(zone_name)

    def clamp_map_scale(self, scale: float) -> float:
        min_scale = 0.05 * max(0.2, float(self.map_zoom_multiplier))
        max_scale = 8.0 * max(0.5, float(self.map_zoom_multiplier))
        return max(min_scale, min(scale, max_scale))

    def get_waypoint_marker_size(self, icon_width: float) -> float:
        marker_zoom = max(0.2, float(self.marker_zoom_multiplier))
        zoom_factor = 0.68 + min(max(self.scale, 0.05), 2.25) * 0.72
        return max(12.0, min(icon_width * 4.25, icon_width * zoom_factor * marker_zoom))

    def setup_fonts(self) -> None:
        font_candidates = [
            Path("C:/Windows/Fonts/segoeui.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/tahoma.ttf"),
        ]
        for font_path in font_candidates:
            if not font_path.exists():
                continue
            with dpg.font_registry(tag="font_registry"):
                with dpg.font(str(font_path), 16) as font:
                    dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                    dpg.add_font_range_hint(dpg.mvFontRangeHint_Cyrillic)
            dpg.bind_font(font)
            break

    def set_status(self, text: str) -> None:
        if dpg.does_item_exist("status_text"):
            dpg.set_value("status_text", text)

    def set_progress(self, text: str) -> None:
        if dpg.does_item_exist("progress_text"):
            dpg.set_value("progress_text", text)

    def to_texture_data(self, image: Image.Image) -> np.ndarray:
        return np.asarray(image.convert("RGBA"), dtype=np.float32).ravel() / 255.0

    def update_overlay_texture(self, width: int, height: int, data: np.ndarray) -> None:
        if dpg.does_item_exist(self.overlay_texture_tag):
            dpg.delete_item(self.overlay_texture_tag)
        dpg.add_static_texture(
            width=width,
            height=height,
            default_value=data,
            tag=self.overlay_texture_tag,
            parent="texture_registry",
        )

    def load_icon_textures(self) -> None:
        for icon_index in sorted(WAYPOINT_ICON_NAMES):
            try:
                icon_path = self.core.ensure_waypoint_icon_png(icon_index)
            except Exception as error:
                self.set_status(self.t("status_icons_error", error=error))
                continue

            with Image.open(icon_path) as image:
                rgba = image.convert("RGBA")
                tag = f"icon_tex_{icon_index}"
                if dpg.does_item_exist(tag):
                    dpg.delete_item(tag)
                dpg.add_static_texture(
                    width=rgba.width,
                    height=rgba.height,
                    default_value=self.to_texture_data(rgba),
                    tag=tag,
                    parent="texture_registry",
                )
                self.icon_textures[icon_index] = TextureInfo(
                    tag=tag,
                    width=rgba.width,
                    height=rgba.height,
                    map_x=0.0,
                    map_y=0.0,
                )

    def load_zone_textures(self) -> None:
        if self.active_map is None:
            return

        for index, zone in enumerate(self.active_map.zones):
            if zone.name not in self.enabled_zone_names:
                continue
            try:
                with Image.open(zone.png_path) as image:
                    rgba = image.convert("RGBA")
                    texture_tag = f"zone_tex_{index}"
                    if dpg.does_item_exist(texture_tag):
                        dpg.delete_item(texture_tag)
                    dpg.add_static_texture(
                        width=rgba.width,
                        height=rgba.height,
                        default_value=self.to_texture_data(rgba),
                        tag=texture_tag,
                        parent="texture_registry",
                    )
                    self.tile_texture_tags.append(texture_tag)
                    self.tile_textures[(index, 0)] = TextureInfo(
                        tag=texture_tag,
                        width=rgba.width,
                        height=rgba.height,
                        map_x=(zone.min_tx - self.active_map.min_x) * self.tile_size,
                        map_y=(zone.min_tz - self.active_map.min_z) * self.tile_size,
                    )
            except Exception as error:
                self.set_status(f"Не удалось загрузить зону {zone.name}: {error}")

    def refresh_zone_list(self) -> None:
        if not dpg.does_item_exist("zone_filter_list"):
            return
        dpg.delete_item("zone_filter_list", children_only=True)
        if self.active_map is None:
            return

        for zone in self.active_map.zones:
            dpg.add_checkbox(
                label=zone.name,
                default_value=zone.name in self.enabled_zone_names,
                callback=self.on_zone_toggle,
                user_data=zone.name,
                parent="zone_filter_list",
            )

    def reload_zone_textures(self) -> None:
        if dpg.does_item_exist("map_drawlist"):
            dpg.delete_item("map_drawlist", children_only=True)
        self.clear_tile_textures()
        self.load_zone_textures()
        self.process_tile_queue()
        self.overlay_cache_key = None
        self.needs_redraw = True

    def enable_all_zones(self) -> None:
        if self.active_map is None:
            return
        self.enabled_zone_names = {zone.name for zone in self.active_map.zones}
        self.refresh_zone_list()
        self.zone_reload_pending = True

    def disable_all_zones(self) -> None:
        self.enabled_zone_names.clear()
        self.refresh_zone_list()
        self.zone_reload_pending = True

    def on_zone_toggle(self, sender, app_data, user_data) -> None:
        zone_name = str(user_data)
        if bool(app_data):
            self.enabled_zone_names.add(zone_name)
        else:
            self.enabled_zone_names.discard(zone_name)
        self.zone_reload_pending = True

    def get_active_map_bounds(self) -> tuple[int, int, int, int]:
        if self.active_map is None:
            return 0, 0, 0, 0
        active_zones = [zone for zone in self.active_map.zones if zone.name in self.enabled_zone_names]
        if not active_zones:
            return self.active_map.min_x, self.active_map.max_x, self.active_map.min_z, self.active_map.max_z
        return (
            min(zone.min_tx for zone in active_zones),
            max(zone.max_tx for zone in active_zones),
            min(zone.min_tz for zone in active_zones),
            max(zone.max_tz for zone in active_zones),
        )

    def get_visible_chunk_keys(self, margin_px: float = 0.0) -> set[tuple[int, int]]:
        if self.active_map is None:
            return set()

        left, top, right, bottom = self.visible_map_rect()
        left -= margin_px
        top -= margin_px
        right += margin_px
        bottom += margin_px

        min_chunk_x = int(math.floor((left + self.active_map.min_x * self.tile_size) / self.tile_size))
        max_chunk_x = int(math.floor((right + self.active_map.min_x * self.tile_size) / self.tile_size))
        min_chunk_z = int(math.floor((top + self.active_map.min_z * self.tile_size) / self.tile_size))
        max_chunk_z = int(math.floor((bottom + self.active_map.min_z * self.tile_size) / self.tile_size))

        return {
            (chunk_x, chunk_z)
            for chunk_x in range(min_chunk_x - self.marker_margin_chunks, max_chunk_x + self.marker_margin_chunks + 1)
            for chunk_z in range(min_chunk_z - self.marker_margin_chunks, max_chunk_z + self.marker_margin_chunks + 1)
        }

    def rebuild_waypoint_index(self) -> None:
        chunks: dict[tuple[int, int], list[dict]] = {}
        for waypoint in self.display_waypoints:
            chunk_key = (waypoint["tile_x"], waypoint["tile_z"])
            chunks.setdefault(chunk_key, []).append(waypoint)
        self.waypoint_chunks = chunks

    def sync_waypoints_from_raw(self) -> None:
        combined: list[dict] = []
        parsed_groups = [
            ("cfg", self.core.parse_waypoints_data(self.raw_waypoints)),
            ("generated", self.core.parse_waypoints_data(self.generated_raw_waypoints)),
        ]
        next_id = 0
        for source, items in parsed_groups:
            for item in items:
                waypoint = dict(item)
                waypoint["id"] = next_id
                waypoint["source"] = source
                waypoint["source_id"] = item["id"]
                next_id += 1
                combined.append(waypoint)

        self.display_waypoints = combined
        self.overlay_cache_key = None
        if self.active_map is not None:
            for waypoint in self.display_waypoints:
                waypoint["map_x"], waypoint["map_y"] = self.waypoint_to_map_px(waypoint)
                waypoint["tile_x"] = int(math.floor(waypoint["pos"]["x"] / self.tile_size))
                waypoint["tile_z"] = int(math.floor(waypoint["pos"]["z"] / self.tile_size))
        else:
            for waypoint in self.display_waypoints:
                waypoint["map_x"], waypoint["map_y"] = 0.0, 0.0
                waypoint["tile_x"] = 0
                waypoint["tile_z"] = 0
        self.rebuild_waypoint_index()
        if self.selected_waypoint_id is not None and self.selected_waypoint_id >= len(self.display_waypoints):
            self.selected_waypoint_id = None
        self.selected_waypoint_ids = {
            item for item in self.selected_waypoint_ids if 0 <= item < len(self.display_waypoints)
        }
        self.cleanup_layers()
        self.refresh_waypoint_list()
        self.refresh_layers_list()
        self.needs_redraw = True

    def load_waypoints(self) -> None:
        self.raw_waypoints = self.core.load_raw_waypoints()
        self.sync_waypoints_from_raw()
        self.load_layers_state()

    def choose_default_map(self) -> str | None:
        maps = self.core.get_maps()
        if not maps:
            return None
        if "map" in maps:
            return "map"
        return sorted(maps)[0]

    def select_map(self, map_id: str) -> None:
        try:
            map_info = self.core.get_map(map_id)
        except KeyError as error:
            self.set_status(str(error))
            return

        self.active_map_id = map_id
        self.active_map = map_info
        self.clear_tile_textures()
        self.tile_queue = deque()

        first_zone = map_info.zones[0] if map_info.zones else None
        if first_zone is None:
            self.set_status(f"{map_id}: нет PNG-зон")
            return
        self.enabled_zone_names = {first_zone.name}

        try:
            if first_zone.tiles_wide > 0:
                self.tile_size = max(1, round(first_zone.image_width / first_zone.tiles_wide))
            else:
                with Image.open(first_zone.png_path) as first_image:
                    self.tile_size = first_image.width
        except Exception as error:
            self.set_status(f"Не удалось прочитать PNG-зону: {error}")
            self.tile_size = 512

        self.tile_queue.clear()
        self.load_zone_textures()
        self.refresh_zone_list()
        min_tx, max_tx, min_tz, max_tz = self.get_active_map_bounds()
        map_w = (max_tx - min_tx + 1) * self.tile_size
        map_h = (max_tz - min_tz + 1) * self.tile_size
        self.camera_x = (min_tx - self.active_map.min_x) * self.tile_size + map_w / 2.0
        self.camera_y = (min_tz - self.active_map.min_z) * self.tile_size + map_h / 2.0
        self.scale = self.clamp_map_scale(INITIAL_ZOOM * self.map_zoom_multiplier)
        self.pending_fit = False
        self.needs_redraw = True
        self.selected_waypoint_id = None
        self.selected_waypoint_ids.clear()
        for waypoint in self.display_waypoints:
            waypoint["map_x"], waypoint["map_y"] = self.waypoint_to_map_px(waypoint)
            waypoint["tile_x"] = int(math.floor(waypoint["pos"]["x"] / self.tile_size))
            waypoint["tile_z"] = int(math.floor(waypoint["pos"]["z"] / self.tile_size))
        self.rebuild_waypoint_index()
        if self.image_path and dpg.does_item_exist(self.image_preview_texture_tag):
            self.reset_image_preview_bounds()
        self.set_status(f"Карта: {map_info.map_id}")
        self.set_progress(f"Зоны в памяти: {len(self.tile_textures)} / {len(map_info.zones)}")
        if dpg.does_item_exist("map_name_text"):
            dpg.set_value("map_name_text", map_info.map_id)
        if dpg.does_item_exist("zoom_text"):
            dpg.set_value("zoom_text", self.t("zoom_label", scale=self.scale))

    def fit_to_map(self) -> None:
        if self.active_map is None:
            return

        viewer_w, viewer_h = self.get_viewer_size()
        if viewer_w <= 0 or viewer_h <= 0:
            return

        min_tx, max_tx, min_tz, max_tz = self.get_active_map_bounds()
        map_w = (max_tx - min_tx + 1) * self.tile_size
        map_h = (max_tz - min_tz + 1) * self.tile_size
        if map_w <= 0 or map_h <= 0:
            return

        self.scale = min((viewer_w - 40) / map_w, (viewer_h - 40) / map_h)
        self.scale = self.clamp_map_scale(self.scale * 0.96 * self.map_zoom_multiplier)
        self.camera_x = (min_tx - self.active_map.min_x) * self.tile_size + map_w / 2.0
        self.camera_y = (min_tz - self.active_map.min_z) * self.tile_size + map_h / 2.0
        self.pending_fit = False
        self.needs_redraw = True
        self.overlay_cache_key = None
        dpg.set_value("zoom_text", self.t("zoom_label", scale=self.scale))

    def center_on_selected_waypoint(self) -> None:
        if self.active_map is None or self.selected_waypoint_id is None:
            return

        waypoint = self.display_waypoints[self.selected_waypoint_id]
        self.camera_x, self.camera_y = self.waypoint_to_map_px(waypoint)
        self.overlay_cache_key = None
        self.needs_redraw = True

    def delete_selected_waypoint(self) -> None:
        if not self.selected_waypoint_ids:
            self.set_status(self.t("status_waypoint_not_selected"))
            return

        self.push_undo_state()

        selected_cfg_ids: set[int] = set()
        selected_generated_ids: set[int] = set()
        for waypoint_id in sorted(self.selected_waypoint_ids):
            if waypoint_id < 0 or waypoint_id >= len(self.display_waypoints):
                continue
            waypoint = self.display_waypoints[waypoint_id]
            if waypoint["source"] == "generated":
                selected_generated_ids.add(int(waypoint["source_id"]))
            else:
                selected_cfg_ids.add(int(waypoint["source_id"]))

        if selected_cfg_ids:
            self.raw_waypoints = [
                item for index, item in enumerate(self.raw_waypoints) if index not in selected_cfg_ids
            ]
        if selected_generated_ids:
            self.generated_raw_waypoints = [
                item
                for index, item in enumerate(self.generated_raw_waypoints)
                if index not in selected_generated_ids
            ]

        self.selected_waypoint_id = None
        self.selected_waypoint_ids.clear()
        self.sync_waypoints_from_raw()
        self.set_status(self.t("status_waypoint_deleted"))

    def save_waypoints(self) -> None:
        try:
            path = self.core.save_waypoints(self.raw_waypoints)
        except Exception as error:
            self.set_status(self.t("status_waypoint_save_error", error=error))
            return

        if hasattr(self, "refresh_exbo_settings_ui"):
            self.refresh_exbo_settings_ui()
        self.set_status(self.t("status_changes_saved", path=path))

    def build_color_dict(self, color_raw: int) -> dict:
        argb = int(color_raw) & 0xFFFFFFFF
        return {
            "argb": argb,
            "a": (argb >> 24) & 0xFF,
            "r": (argb >> 16) & 0xFF,
            "g": (argb >> 8) & 0xFF,
            "b": argb & 0xFF,
            "hex": f"#{(argb >> 16) & 0xFF:02X}{(argb >> 8) & 0xFF:02X}{argb & 0xFF:02X}",
        }

    def update_waypoint_source_style(
        self,
        waypoint: dict,
        icon_index: int,
        color_raw: int,
        name: str | None = None,
    ) -> None:
        source_list = self.generated_raw_waypoints if waypoint["source"] == "generated" else self.raw_waypoints
        source_id = waypoint["source_id"]
        if source_id < 0 or source_id >= len(source_list):
            return
        target = source_list[source_id]
        target["icon_index"] = int(icon_index)
        target["color"] = int(color_raw)
        if name is not None:
            target["name"] = str(name)

    def get_waypoint_icon_labels(self) -> list[str]:
        return [f"{index}: {name}" for index, name in sorted(WAYPOINT_ICON_NAMES.items())]

    def parse_waypoint_icon_value(self, value: object, default: int = 0) -> int:
        try:
            text = str(value)
            return max(0, min(6, int(text.split(":", 1)[0].strip())))
        except Exception:
            try:
                return max(0, min(6, int(value)))
            except Exception:
                return default

    def refresh_selected_waypoint_editor(self) -> None:
        if not dpg.does_item_exist("selected_waypoints_info_text"):
            return

        selected_ids = sorted(
            waypoint_id
            for waypoint_id in self.selected_waypoint_ids
            if 0 <= waypoint_id < len(self.display_waypoints)
        )
        has_selection = bool(selected_ids)
        dpg.set_value("selected_waypoints_info_text", self.t("selected_count", count=len(selected_ids)))
        if dpg.does_item_exist("selected_waypoint_apply_button"):
            dpg.configure_item("selected_waypoint_apply_button", enabled=has_selection)
        if dpg.does_item_exist("selected_waypoint_color_input"):
            dpg.configure_item("selected_waypoint_color_input", enabled=has_selection)
        if dpg.does_item_exist("selected_waypoint_icon_combo"):
            dpg.configure_item("selected_waypoint_icon_combo", enabled=has_selection)
        if dpg.does_item_exist("selected_waypoint_name_input"):
            dpg.configure_item("selected_waypoint_name_input", enabled=has_selection)
        if not has_selection:
            self.selected_waypoint_name_mixed = False
            if dpg.does_item_exist("selected_waypoint_name_note"):
                dpg.set_value("selected_waypoint_name_note", self.t("waypoint_name_note_empty"))
            return

        primary_id = self.selected_waypoint_id if self.selected_waypoint_id in self.selected_waypoint_ids else selected_ids[0]
        waypoint = self.display_waypoints[primary_id]
        color = waypoint["color"]
        if dpg.does_item_exist("selected_waypoint_color_input"):
            dpg.set_value(
                "selected_waypoint_color_input",
                [int(color["r"]), int(color["g"]), int(color["b"]), int(color["a"])],
            )
        if dpg.does_item_exist("selected_waypoint_icon_combo"):
            dpg.set_value(
                "selected_waypoint_icon_combo",
                f"{int(waypoint['iconIndex'])}: {WAYPOINT_ICON_NAMES.get(int(waypoint['iconIndex']), 'unknown')}",
            )
        names = [str(self.display_waypoints[waypoint_id]["name"]) for waypoint_id in selected_ids]
        unique_names = sorted(set(names))
        self.selected_waypoint_name_mixed = len(unique_names) > 1
        if dpg.does_item_exist("selected_waypoint_name_input"):
            dpg.set_value("selected_waypoint_name_input", "" if self.selected_waypoint_name_mixed else unique_names[0])
        if dpg.does_item_exist("selected_waypoint_name_note"):
            dpg.set_value(
                "selected_waypoint_name_note",
                self.t("waypoint_name_note_mixed")
                if self.selected_waypoint_name_mixed
                else self.t("waypoint_name_note_apply"),
            )

    def apply_style_to_selected_waypoints(self) -> None:
        selected_ids = sorted(
            waypoint_id
            for waypoint_id in self.selected_waypoint_ids
            if 0 <= waypoint_id < len(self.display_waypoints)
        )
        if not selected_ids:
            self.set_status(self.t("status_select_waypoints_first"))
            return

        rgba = list(dpg.get_value("selected_waypoint_color_input")) if dpg.does_item_exist("selected_waypoint_color_input") else [255, 255, 255, 255]
        r, g, b, a = [max(0, min(255, int(v))) for v in (rgba + [255, 255, 255, 255])[:4]]
        icon_index = 0
        if dpg.does_item_exist("selected_waypoint_icon_combo"):
            icon_value = str(dpg.get_value("selected_waypoint_icon_combo"))
            try:
                icon_index = max(0, min(6, int(icon_value.split(":", 1)[0].strip())))
            except Exception:
                icon_index = 0
        name_value = ""
        if dpg.does_item_exist("selected_waypoint_name_input"):
            name_value = str(dpg.get_value("selected_waypoint_name_input"))
        should_apply_name = (not self.selected_waypoint_name_mixed) or bool(name_value.strip())
        color_raw = ((a & 0xFF) << 24) | ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF)

        self.push_undo_state()
        for waypoint_id in selected_ids:
            waypoint = self.display_waypoints[waypoint_id]
            self.update_waypoint_source_style(
                waypoint,
                icon_index,
                color_raw,
                name=name_value if should_apply_name else None,
            )
            waypoint["iconIndex"] = int(icon_index)
            waypoint["iconName"] = WAYPOINT_ICON_NAMES.get(int(icon_index), "unknown")
            waypoint["colorRaw"] = int(color_raw)
            waypoint["color"] = self.build_color_dict(color_raw)
            if should_apply_name:
                waypoint["name"] = name_value

        self.refresh_waypoint_list()
        self.overlay_cache_key = None
        self.needs_redraw = True
        self.set_status(self.t("status_style_applied", count=len(selected_ids)))

    def on_apply_selected_waypoint_style_clicked(self, sender, app_data, user_data=None) -> None:
        self.apply_style_to_selected_waypoints()

    def create_waypoint_at_view_center(self) -> None:
        if self.active_map is None:
            self.set_status(self.t("status_open_map_first"))
            return

        rgba = (
            list(dpg.get_value("new_waypoint_color_input"))
            if dpg.does_item_exist("new_waypoint_color_input")
            else [255, 255, 255, 255]
        )
        r, g, b, a = [max(0, min(255, int(v))) for v in (rgba + [255, 255, 255, 255])[:4]]
        icon_index = self.parse_waypoint_icon_value(
            dpg.get_value("new_waypoint_icon_combo") if dpg.does_item_exist("new_waypoint_icon_combo") else 0
        )
        name_value = ""
        if dpg.does_item_exist("new_waypoint_name_input"):
            name_value = str(dpg.get_value("new_waypoint_name_input")).strip()

        world_x = self.camera_x + self.active_map.min_x * self.tile_size
        world_z = self.camera_y + self.active_map.min_z * self.tile_size
        color_raw = ((a & 0xFF) << 24) | ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF)
        next_time = 1_700_000_000_000 + len(self.raw_waypoints) + len(self.generated_raw_waypoints)

        self.push_undo_state()
        self.raw_waypoints.append(
            {
                "color": int(color_raw),
                "can_position_float": True,
                "time": int(next_time),
                "icon_index": int(icon_index),
                "pos": {"x": float(world_x), "y": 70.0, "z": float(world_z)},
                "name": name_value,
                "type": "manual",
            }
        )
        new_source_id = len(self.raw_waypoints) - 1
        self.sync_waypoints_from_raw()
        for waypoint in self.display_waypoints:
            if waypoint["source"] == "cfg" and int(waypoint["source_id"]) == new_source_id:
                self.update_selection_state({int(waypoint["id"])}, primary_id=int(waypoint["id"]))
                break
        self.center_on_selected_waypoint()
        self.set_status(self.t("status_waypoint_created"))

    def on_create_waypoint_clicked(self, sender, app_data, user_data=None) -> None:
        self.create_waypoint_at_view_center()

    def current_center_tile(self) -> tuple[float, float]:
        if self.active_map is None:
            return 0.0, 0.0
        local_tile_x = self.camera_x / self.tile_size
        local_tile_z = self.camera_y / self.tile_size
        return self.active_map.min_x + local_tile_x, self.active_map.min_z + local_tile_z

    def tile_to_world(self, tile_x: float, tile_z: float) -> tuple[float, float]:
        return tile_x * self.tile_size, tile_z * self.tile_size

    def update_generated_status(self, text: str) -> None:
        if dpg.does_item_exist("generated_status"):
            dpg.set_value("generated_status", text)

    def invalidate_image_marker_preview(self) -> None:
        self.image_preview_marker_cache_key = None
        self.image_preview_marker_cache_points = []
        self.image_preview_marker_cache_size = (0, 0)
        self.needs_redraw = True

    def update_image_marker_estimate(self, count: int | None = None) -> None:
        if not dpg.does_item_exist("image_marker_estimate_text"):
            return
        if count is None:
            dpg.set_value("image_marker_estimate_text", "Превью маркеров: -")
        else:
            dpg.set_value("image_marker_estimate_text", f"Превью маркеров: {count}")

    def configure_image_settings_visibility(self) -> None:
        contour_only = bool(dpg.get_value("image_contour_only_input")) if dpg.does_item_exist("image_contour_only_input") else False
        include_background = bool(dpg.get_value("image_include_background_input")) if dpg.does_item_exist("image_include_background_input") else False
        for tag in (
            "image_brightness_cutoff_label",
            "image_brightness_cutoff_input",
            "image_contour_thickness_label",
            "image_contour_thickness_input",
            "image_contour_help_text",
        ):
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, show=contour_only)
        for tag in ("image_alpha_cutoff_label", "image_alpha_cutoff_input"):
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, show=not include_background)

    def on_image_settings_changed(self, sender=None, app_data=None, user_data=None) -> None:
        self.configure_image_settings_visibility()
        self.invalidate_image_marker_preview()
        if not self.image_path:
            self.update_image_marker_estimate(None)

    def capture_history_state(self) -> dict:
        return {
            "raw_waypoints": copy.deepcopy(self.raw_waypoints),
            "generated_raw_waypoints": copy.deepcopy(self.generated_raw_waypoints),
            "selected_waypoint_id": self.selected_waypoint_id,
            "selected_waypoint_ids": set(self.selected_waypoint_ids),
            "image_preview_bounds_map": self.image_preview_bounds_map,
            "image_preview_selected": self.image_preview_selected,
        }

    def restore_history_state(self, state: dict) -> None:
        self.raw_waypoints = copy.deepcopy(state["raw_waypoints"])
        self.generated_raw_waypoints = copy.deepcopy(state["generated_raw_waypoints"])
        self.image_preview_bounds_map = state.get("image_preview_bounds_map")
        self.image_preview_selected = bool(state.get("image_preview_selected", False))
        self.selected_waypoint_id = state.get("selected_waypoint_id")
        self.selected_waypoint_ids = set(state.get("selected_waypoint_ids", set()))
        self.sync_waypoints_from_raw()
        self.overlay_cache_key = None
        self.needs_redraw = True

    def push_undo_state(self) -> None:
        self.undo_stack.append(self.capture_history_state())
        if len(self.undo_stack) > UNDO_HISTORY_LIMIT:
            self.undo_stack = self.undo_stack[-UNDO_HISTORY_LIMIT:]
        self.redo_stack.clear()

    def undo(self) -> None:
        if not self.undo_stack:
            self.set_status(self.t("status_undo_empty"))
            return
        self.redo_stack.append(self.capture_history_state())
        self.restore_history_state(self.undo_stack.pop())
        self.set_status(self.t("status_undo_done"))

    def redo(self) -> None:
        if not self.redo_stack:
            self.set_status(self.t("status_redo_empty"))
            return
        self.undo_stack.append(self.capture_history_state())
        self.restore_history_state(self.redo_stack.pop())
        self.set_status(self.t("status_redo_done"))

    def clear_image_preview(self) -> None:
        if dpg.does_item_exist("map_drawlist"):
            dpg.delete_item("map_drawlist", children_only=True)
        self.image_preview_bounds_map = None
        self.image_preview_selected = False
        self.image_preview_drag_mode = None
        self.image_preview_drag_initial_bounds = None
        self.image_preview_texture_size = (0, 0)
        self.image_preview_source_size = (0, 0)
        if dpg.does_item_exist(self.image_preview_texture_tag):
            dpg.delete_item(self.image_preview_texture_tag)
        self.invalidate_image_marker_preview()
        self.update_image_marker_estimate(None)
        self.needs_redraw = True

    def get_auto_image_resolution(self, source_w: int, source_h: int) -> tuple[int, int]:
        if source_w <= 0 or source_h <= 0:
            return DEFAULT_IMAGE_RESOLUTION, DEFAULT_IMAGE_RESOLUTION
        if max(source_w, source_h) <= IMAGE_AUTO_RESOLUTION_MAX_DIM:
            return source_w, source_h
        if source_w >= source_h:
            target_w = IMAGE_AUTO_RESOLUTION_MAX_DIM
            target_h = max(1, round(source_h * (target_w / source_w)))
        else:
            target_h = IMAGE_AUTO_RESOLUTION_MAX_DIM
            target_w = max(1, round(source_w * (target_h / source_h)))
        return target_w, target_h

    def get_effective_max_markers(self, mask: np.ndarray) -> int:
        _ = mask
        return max(1, min(100000, int(dpg.get_value("image_marker_limit_input"))))

    def build_image_mask(self, rgba_data: np.ndarray) -> np.ndarray:
        alpha_cutoff = max(0, min(255, int(dpg.get_value("image_alpha_cutoff_input"))))
        brightness_cutoff = max(0, min(255, int(dpg.get_value("image_brightness_cutoff_input"))))
        include_background = bool(dpg.get_value("image_include_background_input")) if dpg.does_item_exist("image_include_background_input") else False

        if include_background:
            mask = np.ones((rgba_data.shape[0], rgba_data.shape[1]), dtype=bool)
        else:
            alpha = rgba_data[:, :, 3]
            mask = alpha >= alpha_cutoff
        if brightness_cutoff > 0:
            rgb = rgba_data[:, :, :3].astype(np.float32)
            brightness = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]).astype(np.uint8)
            mask &= brightness >= brightness_cutoff
        return mask

    def extract_contour_mask(self, mask: np.ndarray, thickness: int) -> np.ndarray:
        if mask.size == 0:
            return mask

        padded = np.pad(mask, 1, constant_values=False)
        center = padded[1:-1, 1:-1]
        neighbors = [
            padded[:-2, 1:-1],
            padded[2:, 1:-1],
            padded[1:-1, :-2],
            padded[1:-1, 2:],
            padded[:-2, :-2],
            padded[:-2, 2:],
            padded[2:, :-2],
            padded[2:, 2:],
        ]
        edge = center & (~np.logical_and.reduce(neighbors))

        result = edge.copy()
        for _ in range(max(0, thickness - 1)):
            expanded = result.copy()
            expanded[:-1, :] |= result[1:, :]
            expanded[1:, :] |= result[:-1, :]
            expanded[:, :-1] |= result[:, 1:]
            expanded[:, 1:] |= result[:, :-1]
            expanded[:-1, :-1] |= result[1:, 1:]
            expanded[:-1, 1:] |= result[1:, :-1]
            expanded[1:, :-1] |= result[:-1, 1:]
            expanded[1:, 1:] |= result[:-1, :-1]
            result = expanded & mask
        return result

    def collect_marker_pixels(
        self,
        rgba_data: np.ndarray,
        mask: np.ndarray,
        max_markers: int,
        sampling_step: int = 1,
    ) -> list[tuple[int, int, int, int, int]]:
        pixels: list[tuple[int, int, int, int, int]] = []
        height, width = mask.shape
        sampling_step = max(1, int(sampling_step))

        if sampling_step > 1:
            for y0 in range(0, height, sampling_step):
                y1 = min(height, y0 + sampling_step)
                for x0 in range(0, width, sampling_step):
                    x1 = min(width, x0 + sampling_step)
                    sub_mask = mask[y0:y1, x0:x1]
                    if not np.any(sub_mask):
                        continue
                    ys, xs = np.nonzero(sub_mask)
                    py = y0 + int(ys[0])
                    px = x0 + int(xs[0])
                    pixels.append(
                        (
                            px,
                            py,
                            int(rgba_data[py, px, 0]),
                            int(rgba_data[py, px, 1]),
                            int(rgba_data[py, px, 2]),
                        )
                    )
        else:
            ys, xs = np.nonzero(mask)
            if len(xs) == 0:
                return []
            pixels = [
                (
                    int(x),
                    int(y),
                    int(rgba_data[y, x, 0]),
                    int(rgba_data[y, x, 1]),
                    int(rgba_data[y, x, 2]),
                )
                for y, x in zip(ys.tolist(), xs.tolist())
            ]

        if len(pixels) <= max_markers:
            return pixels

        cell_size = max(1.0, math.sqrt(len(pixels) / max_markers))
        buckets: dict[tuple[int, int], tuple[int, int, int, int, int]] = {}
        for item in pixels:
            cell = (int(item[0] / cell_size), int(item[1] / cell_size))
            if cell not in buckets:
                buckets[cell] = item

        limited = list(buckets.values())
        if len(limited) > max_markers:
            stride = len(limited) / max_markers
            limited = [limited[min(len(limited) - 1, int(index * stride))] for index in range(max_markers)]
        return limited

    def get_marker_preview_data(self) -> tuple[list[tuple[int, int, int, int, int]], int, int]:
        if not self.image_path:
            self.update_image_marker_estimate(None)
            return [], 0, 0

        candidate = Path(self.image_path)
        if not candidate.exists():
            self.update_image_marker_estimate(None)
            return [], 0, 0

        contour_only = bool(dpg.get_value("image_contour_only_input"))
        contour_thickness = max(1, min(8, int(dpg.get_value("image_contour_thickness_input"))))
        sampling_step = max(1, min(32, int(dpg.get_value("image_sampling_step_input"))))
        max_markers = max(1, min(100000, int(dpg.get_value("image_marker_limit_input"))))
        include_background = bool(dpg.get_value("image_include_background_input")) if dpg.does_item_exist("image_include_background_input") else False
        preview_bounds_key = None
        if self.image_preview_bounds_map is not None:
            preview_bounds_key = tuple(round(float(v), 2) for v in self.image_preview_bounds_map)
        cache_key = (
            str(candidate),
            candidate.stat().st_mtime_ns,
            contour_only,
            contour_thickness,
            sampling_step,
            include_background,
            preview_bounds_key,
            int(dpg.get_value("image_alpha_cutoff_input")),
            int(dpg.get_value("image_brightness_cutoff_input")),
            max_markers,
        )

        if self.image_preview_marker_cache_key == cache_key:
            self.update_image_marker_estimate(len(self.image_preview_marker_cache_points))
            w, h = self.image_preview_marker_cache_size
            return list(self.image_preview_marker_cache_points), w, h

        try:
            with Image.open(candidate) as source_image:
                source_rgba = source_image.convert("RGBA")
                base_w, base_h = self.get_auto_image_resolution(source_rgba.width, source_rgba.height)
                image = source_rgba.resize((base_w, base_h), Image.Resampling.LANCZOS)
        except Exception:
            self.update_image_marker_estimate(None)
            return [], 0, 0

        data = np.asarray(image, dtype=np.uint8)
        mask = self.build_image_mask(data)
        if contour_only:
            mask = self.extract_contour_mask(mask, contour_thickness)

        max_markers = self.get_effective_max_markers(mask)
        image = self.prepare_marker_source_image(image, max_markers)
        data = np.asarray(image, dtype=np.uint8)
        mask = self.build_image_mask(data)
        if contour_only:
            mask = self.extract_contour_mask(mask, contour_thickness)
        target_h, target_w = mask.shape

        effective_step = sampling_step
        if self.image_preview_bounds_map is not None and target_w > 0 and target_h > 0:
            x1, y1, x2, y2 = self.image_preview_bounds_map
            preview_w = max(1.0, abs(x2 - x1))
            preview_h = max(1.0, abs(y2 - y1))
            map_px_per_img_px = max(preview_w / target_w, preview_h / target_h)
            effective_step = max(1, int(round(sampling_step / max(map_px_per_img_px, 1e-3))))

        pixels = self.collect_marker_pixels(data, mask, max_markers, sampling_step=effective_step)
        self.image_preview_marker_cache_key = cache_key
        self.image_preview_marker_cache_points = list(pixels)
        self.image_preview_marker_cache_size = (target_w, target_h)
        self.update_image_marker_estimate(len(pixels))
        return pixels, target_w, target_h

    def prepare_marker_source_image(self, source_rgba: Image.Image, max_markers: int) -> Image.Image:
        target_w, target_h = self.get_auto_image_resolution(source_rgba.width, source_rgba.height)
        image = source_rgba.resize((target_w, target_h), Image.Resampling.LANCZOS)

        while True:
            alpha = np.asarray(image.getchannel("A"), dtype=np.uint8)
            opaque_count = int(np.count_nonzero(alpha >= 22))
            if opaque_count <= max_markers or image.width <= 8 or image.height <= 8:
                return image

            scale = math.sqrt(max_markers / max(opaque_count, 1))
            next_w = max(8, min(image.width - 1, round(image.width * scale)))
            next_h = max(8, min(image.height - 1, round(image.height * scale)))
            if next_w == image.width and next_h == image.height:
                return image
            image = image.resize((next_w, next_h), Image.Resampling.BOX)

    def reset_image_preview_bounds(self) -> None:
        if self.active_map is None or self.image_preview_source_size[0] <= 0 or self.image_preview_source_size[1] <= 0:
            self.image_preview_bounds_map = None
            return

        viewer_w, _ = self.get_viewer_size()
        visible_map_w = viewer_w / max(self.scale, 0.001) if viewer_w > 0 else self.tile_size * 6.0
        preview_w = max(self.tile_size * 2.0, min(self.tile_size * 8.0, visible_map_w * 0.28))
        aspect = self.image_preview_source_size[1] / max(1, self.image_preview_source_size[0])
        preview_h = max(IMAGE_PREVIEW_MIN_SIZE_MAP_PX, preview_w * aspect)
        center_x, center_y = self.camera_x, self.camera_y
        self.image_preview_bounds_map = (
            center_x - preview_w / 2.0,
            center_y - preview_h / 2.0,
            center_x + preview_w / 2.0,
            center_y + preview_h / 2.0,
        )
        self.image_preview_selected = True
        self.needs_redraw = True

    def load_image_preview_texture(self, path: Path) -> None:
        self.clear_image_preview()
        with Image.open(path) as source_image:
            rgba = source_image.convert("RGBA")
            self.image_preview_source_size = (rgba.width, rgba.height)
            preview = rgba.copy()
            max_dim = max(preview.width, preview.height)
            if max_dim > IMAGE_PREVIEW_TEXTURE_MAX_DIM:
                scale = IMAGE_PREVIEW_TEXTURE_MAX_DIM / max_dim
                preview = preview.resize(
                    (max(1, round(preview.width * scale)), max(1, round(preview.height * scale))),
                    Image.Resampling.LANCZOS,
                )
            self.image_preview_texture_size = (preview.width, preview.height)
            dpg.add_static_texture(
                width=preview.width,
                height=preview.height,
                default_value=self.to_texture_data(preview),
                tag=self.image_preview_texture_tag,
                parent="texture_registry",
            )

    def get_image_preview_screen_rect(self) -> tuple[float, float, float, float] | None:
        if self.image_preview_bounds_map is None:
            return None
        x1, y1, x2, y2 = self.image_preview_bounds_map
        sx1, sy1 = self.map_to_screen(x1, y1)
        sx2, sy2 = self.map_to_screen(x2, y2)
        return min(sx1, sx2), min(sy1, sy2), max(sx1, sx2), max(sy1, sy2)

    def hit_test_image_preview(self, local_x: float, local_y: float) -> str | None:
        rect = self.get_image_preview_screen_rect()
        if rect is None:
            return None
        x1, y1, x2, y2 = rect
        handle = IMAGE_PREVIEW_HANDLE_SCREEN_PX
        corners = {
            "resize_nw": (x1, y1),
            "resize_ne": (x2, y1),
            "resize_sw": (x1, y2),
            "resize_se": (x2, y2),
        }
        for mode, (cx, cy) in corners.items():
            if abs(local_x - cx) <= handle and abs(local_y - cy) <= handle:
                return mode
        if x1 <= local_x <= x2 and y1 <= local_y <= y2:
            return "move"
        return None

    def update_image_preview_transform(self, map_x: float, map_y: float) -> None:
        if self.image_preview_drag_mode is None or self.image_preview_drag_initial_bounds is None:
            return
        x1, y1, x2, y2 = self.image_preview_drag_initial_bounds
        dx = map_x - self.image_preview_drag_start_map[0]
        dy = map_y - self.image_preview_drag_start_map[1]

        if self.image_preview_drag_mode == "move":
            bounds = (x1 + dx, y1 + dy, x2 + dx, y2 + dy)
        elif self.image_preview_drag_mode == "resize_nw":
            bounds = (x1 + dx, y1 + dy, x2, y2)
        elif self.image_preview_drag_mode == "resize_ne":
            bounds = (x1, y1 + dy, x2 + dx, y2)
        elif self.image_preview_drag_mode == "resize_sw":
            bounds = (x1 + dx, y1, x2, y2 + dy)
        else:
            bounds = (x1, y1, x2 + dx, y2 + dy)

        bx1, by1, bx2, by2 = bounds
        if bx2 - bx1 < IMAGE_PREVIEW_MIN_SIZE_MAP_PX:
            if "w" in self.image_preview_drag_mode:
                bx1 = bx2 - IMAGE_PREVIEW_MIN_SIZE_MAP_PX
            else:
                bx2 = bx1 + IMAGE_PREVIEW_MIN_SIZE_MAP_PX
        if by2 - by1 < IMAGE_PREVIEW_MIN_SIZE_MAP_PX:
            if "n" in self.image_preview_drag_mode:
                by1 = by2 - IMAGE_PREVIEW_MIN_SIZE_MAP_PX
            else:
                by2 = by1 + IMAGE_PREVIEW_MIN_SIZE_MAP_PX

        self.image_preview_bounds_map = (bx1, by1, bx2, by2)
        self.overlay_cache_key = None
        self.invalidate_image_marker_preview()
        self.needs_redraw = True

    def apply_optimization_settings(self) -> None:
        self.max_markers_on_screen = max(1, int(dpg.get_value("marker_screen_limit_input")))
        self.square_render_threshold = max(1, int(dpg.get_value("marker_square_threshold_input")))
        self.overlay_cache_key = None
        self.needs_redraw = True
        self.set_status(
            f"Оптимизация: screen {self.max_markers_on_screen}, squares after {self.square_render_threshold}"
        )

    def load_image_from_path(self, path: str) -> None:
        path = path.strip()
        if not path:
            return
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = (PROJECT_ROOT / candidate).resolve()
        if not candidate.exists():
            self.set_status(f"Картинка не найдена: {candidate}")
            return
        self.image_path = str(candidate)
        if dpg.does_item_exist("image_path_input"):
            dpg.set_value("image_path_input", self.image_path)
        try:
            self.load_image_preview_texture(candidate)
        except Exception as error:
            self.set_status(f"Не удалось загрузить preview картинки: {error}")
            return
        self.invalidate_image_marker_preview()
        self.configure_image_settings_visibility()
        self.reset_image_preview_bounds()
        auto_w, auto_h = self.get_auto_image_resolution(*self.image_preview_source_size)
        self.update_generated_status(
            f"Источник: {candidate.name} | auto res {auto_w}x{auto_h} | drag/resize на карте"
        )
        self.needs_redraw = True

    def generate_markers_from_image(self) -> None:
        if not self.image_path:
            self.update_generated_status("Сначала выбери картинку")
            return
        if self.active_map is None:
            self.update_generated_status("Сначала открой карту")
            return
        if self.image_preview_bounds_map is None:
            self.update_generated_status("Сначала размести картинку на карте")
            return

        fixed_icon_index = max(0, min(6, int(dpg.get_value("image_icon_input"))))
        use_auto_icons = bool(dpg.get_value("image_auto_icons_input"))
        contour_only = bool(dpg.get_value("image_contour_only_input"))
        opaque_pixels, target_w, target_h = self.get_marker_preview_data()

        if not opaque_pixels:
            self.update_generated_status("После отсечения в картинке не осталось подходящих пикселей")
            return

        preview_x1, preview_y1, preview_x2, preview_y2 = self.image_preview_bounds_map
        preview_w = max(1.0, preview_x2 - preview_x1)
        preview_h = max(1.0, preview_y2 - preview_y1)
        generated: list[dict] = []
        for index, (x, y, r, g, b) in enumerate(opaque_pixels):
            u = (x + 0.5) / target_w
            v = (y + 0.5) / target_h
            map_x = preview_x1 + u * preview_w
            map_y = preview_y1 + v * preview_h
            world_x = map_x + self.active_map.min_x * self.tile_size
            world_z = map_y + self.active_map.min_z * self.tile_size
            icon_index = index % len(WAYPOINT_ICON_NAMES) if use_auto_icons else fixed_icon_index
            color_raw = ((255 << 24) | (r << 16) | (g << 8) | b) | 0
            generated.append(
                {
                    "color": int(color_raw),
                    "can_position_float": True,
                    "time": int(1_700_000_000_000 + index),
                    "icon_index": int(icon_index),
                    "pos": {"x": float(world_x), "y": 70.0, "z": float(world_z)},
                    "name": "",
                    "type": "manual",
                }
            )

        self.push_undo_state()
        self.generated_raw_waypoints = generated
        self.sync_waypoints_from_raw()
        self.clear_image_preview()
        self.update_generated_status(
            f"Сгенерировано: {len(generated)} меток, res {target_w}x{target_h}, "
            f"{'контур' if contour_only else 'заливка'}"
        )

    def clear_generated_waypoints(self) -> None:
        if not self.generated_raw_waypoints:
            return
        self.push_undo_state()
        self.generated_raw_waypoints = []
        self.sync_waypoints_from_raw()
        self.update_generated_status("Буфер генерации очищен")

    def bake_generated_waypoints(self) -> None:
        if not self.generated_raw_waypoints:
            self.update_generated_status("Буфер генерации пуст")
            return
        self.push_undo_state()
        baked_count = len(self.generated_raw_waypoints)
        self.raw_waypoints.extend(self.generated_raw_waypoints)
        self.generated_raw_waypoints = []
        self.sync_waypoints_from_raw()
        self.update_generated_status(f"Запечено в основной список: {baked_count} меток")

    def reload_all(self) -> None:
        self.core.get_maps(reload=True)
        self.refresh_map_combo()
        self.load_waypoints()
        next_map = self.active_map_id or self.choose_default_map()
        if next_map:
            self.select_map(next_map)

    def on_map_changed(self, sender, app_data, user_data=None) -> None:
        if app_data:
            self.select_map(app_data)

    def on_reload_clicked(self, sender, app_data, user_data) -> None:
        self.reload_all()

    def on_fit_clicked(self, sender, app_data, user_data) -> None:
        self.fit_to_map()

    def on_save_changes_clicked(self, sender, app_data, user_data) -> None:
        self.save_waypoints()

    def on_center_selected_clicked(self, sender, app_data, user_data) -> None:
        self.center_on_selected_waypoint()

    def on_delete_selected_clicked(self, sender, app_data, user_data) -> None:
        self.delete_selected_waypoint()

    def on_apply_optimization_clicked(self, sender, app_data, user_data) -> None:
        self.apply_optimization_settings()

    def on_image_picked(self, sender, app_data, user_data=None) -> None:
        file_path = app_data.get("file_path_name")
        if file_path:
            self.load_image_from_path(file_path)

    def on_open_image_clicked(self, sender, app_data, user_data) -> None:
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        file_path = filedialog.askopenfilename(
            title="Выбрать изображение",
            filetypes=[
                ("Images", "*.png;*.jpg;*.jpeg;*.webp;*.bmp"),
                ("PNG", "*.png"),
                ("JPEG", "*.jpg;*.jpeg"),
                ("WEBP", "*.webp"),
                ("All files", "*.*"),
            ],
        )
        root.destroy()
        if file_path:
            self.load_image_from_path(file_path)

    def on_generate_image_clicked(self, sender, app_data, user_data) -> None:
        self.generate_markers_from_image()

    def on_clear_generated_clicked(self, sender, app_data, user_data) -> None:
        self.clear_generated_waypoints()

    def on_bake_generated_clicked(self, sender, app_data, user_data) -> None:
        self.bake_generated_waypoints()

    def on_toggle_waypoint_list_clicked(self, sender, app_data, user_data) -> None:
        self.show_waypoint_list = not self.show_waypoint_list
        dpg.configure_item("waypoint_list", show=self.show_waypoint_list)
        dpg.set_item_label(
            "toggle_waypoint_list_button",
            "Hide waypoint list" if self.show_waypoint_list else "Show waypoint list",
        )

    def on_waypoint_selected(self, sender, app_data, user_data) -> None:
        self.selected_waypoint_id = int(user_data)
        self.selected_waypoint_ids = {self.selected_waypoint_id}
        self.refresh_waypoint_list()
        self.refresh_selected_waypoint_editor()
        self.center_on_selected_waypoint()
        self.needs_redraw = True

    def waypoint_layer_key(self, waypoint: dict) -> tuple[str, int]:
        return str(waypoint["source"]), int(waypoint["source_id"])

    def cleanup_layers(self) -> None:
        valid_keys = {self.waypoint_layer_key(item) for item in self.display_waypoints}
        for layer_name in list(self.marker_layers.keys()):
            members = self.marker_layers[layer_name]
            filtered = {item for item in members if item in valid_keys}
            if filtered:
                self.marker_layers[layer_name] = filtered
                self.layer_visibility.setdefault(layer_name, True)
            else:
                self.marker_layers.pop(layer_name, None)
                self.layer_visibility.pop(layer_name, None)

    def is_waypoint_visible_by_layers(self, waypoint: dict) -> bool:
        if not self.marker_layers:
            return True
        key = self.waypoint_layer_key(waypoint)
        owner_layers = [name for name, members in self.marker_layers.items() if key in members]
        if not owner_layers:
            return True
        return any(self.layer_visibility.get(name, True) for name in owner_layers)

    def refresh_layers_list(self) -> None:
        if not dpg.does_item_exist("layers_list"):
            return
        dpg.delete_item("layers_list", children_only=True)
        for layer_name in sorted(self.marker_layers):
            with dpg.group(horizontal=True, parent="layers_list"):
                dpg.add_checkbox(
                    default_value=self.layer_visibility.get(layer_name, True),
                    callback=self.on_layer_visibility_changed,
                    user_data=layer_name,
                )
                dpg.add_button(
                    label=f"{layer_name} ({len(self.marker_layers[layer_name])})",
                    callback=self.select_layer_waypoints,
                    user_data=layer_name,
                    width=-1,
                )

    def on_layer_visibility_changed(self, sender, app_data, user_data) -> None:
        layer_name = str(user_data)
        self.layer_visibility[layer_name] = bool(app_data)
        self.needs_redraw = True

    def select_layer_waypoints(self, sender, app_data, user_data) -> None:
        layer_name = str(user_data)
        members = self.marker_layers.get(layer_name, set())
        selected: set[int] = set()
        for waypoint in self.display_waypoints:
            if self.waypoint_layer_key(waypoint) in members:
                selected.add(int(waypoint["id"]))
        self.update_selection_state(selected, primary_id=next(iter(selected), None))

    def add_selection_to_layer(self) -> None:
        if not self.selected_waypoint_ids:
            self.set_status("Сначала выдели метки для слоя")
            return
        layer_name = ""
        if dpg.does_item_exist("layer_name_input"):
            layer_name = str(dpg.get_value("layer_name_input")).strip()
        if not layer_name:
            layer_name = f"Layer {self.layer_counter}"
            self.layer_counter += 1
            if dpg.does_item_exist("layer_name_input"):
                dpg.set_value("layer_name_input", layer_name)

        members = self.marker_layers.setdefault(layer_name, set())
        for waypoint_id in self.selected_waypoint_ids:
            if 0 <= waypoint_id < len(self.display_waypoints):
                members.add(self.waypoint_layer_key(self.display_waypoints[waypoint_id]))
        self.layer_visibility[layer_name] = True
        self.refresh_layers_list()
        self.set_status(f"Слой '{layer_name}': добавлено {len(self.selected_waypoint_ids)}")

    def get_selectable_waypoints(self, margin_px: float = 128.0) -> list[dict]:
        if not self.display_waypoints:
            return []

        left, top, right, bottom = self.visible_map_rect()
        left -= margin_px
        top -= margin_px
        right += margin_px
        bottom += margin_px

        allowed_chunks = self.get_visible_chunk_keys(margin_px=margin_px)

        visible: list[dict] = []
        for chunk_key in allowed_chunks:
            for waypoint in self.waypoint_chunks.get(chunk_key, []):
                if not self.is_waypoint_visible_by_layers(waypoint):
                    continue
                if left <= waypoint["map_x"] <= right and top <= waypoint["map_y"] <= bottom:
                    visible.append(waypoint)
        return visible

    def find_waypoint_at(self, local_x: float, local_y: float) -> int | None:
        best_id: int | None = None
        best_distance = 1e9

        for waypoint in self.get_selectable_waypoints(margin_px=96.0):
            screen_x, screen_y = self.map_to_screen(waypoint["map_x"], waypoint["map_y"])
            icon = self.icon_textures.get(waypoint["iconIndex"], self.icon_textures.get(0))
            base_size = icon.width if icon else 18
            marker_size = self.get_waypoint_marker_size(base_size)
            distance = math.hypot(local_x - screen_x, local_y - screen_y)
            if distance <= marker_size * 0.75 and distance < best_distance:
                best_distance = distance
                best_id = waypoint["id"]

        return best_id

    def is_shift_pressed(self) -> bool:
        return dpg.is_key_down(dpg.mvKey_LShift) or dpg.is_key_down(dpg.mvKey_RShift)

    def update_selection_state(self, ids: set[int], primary_id: int | None = None) -> None:
        filtered = {item for item in ids if 0 <= item < len(self.display_waypoints)}
        self.selected_waypoint_ids = filtered
        if primary_id is not None and primary_id in filtered:
            self.selected_waypoint_id = primary_id
        elif self.selected_waypoint_id not in filtered:
            self.selected_waypoint_id = next(iter(filtered), None)
        self.overlay_cache_key = None
        self.refresh_waypoint_list()
        self.refresh_selected_waypoint_editor()
        self.needs_redraw = True

    def build_selection_snapshot(self) -> None:
        snapshot: list[dict] = []
        for waypoint_id in sorted(self.selected_waypoint_ids):
            if waypoint_id < 0 or waypoint_id >= len(self.display_waypoints):
                continue
            waypoint = self.display_waypoints[waypoint_id]
            snapshot.append(
                {
                    "id": waypoint_id,
                    "map_x": float(waypoint["map_x"]),
                    "map_y": float(waypoint["map_y"]),
                }
            )
        self.selection_drag_snapshot = snapshot

    def apply_selection_move(self, delta_map_x: float, delta_map_y: float) -> None:
        if self.active_map is None:
            return

        map_offset_x = self.active_map.min_x * self.tile_size
        map_offset_y = self.active_map.min_z * self.tile_size
        for item in self.selection_drag_snapshot:
            waypoint_id = item["id"]
            if waypoint_id < 0 or waypoint_id >= len(self.display_waypoints):
                continue
            waypoint = self.display_waypoints[waypoint_id]
            new_map_x = item["map_x"] + delta_map_x
            new_map_y = item["map_y"] + delta_map_y
            world_x = new_map_x + map_offset_x
            world_z = new_map_y + map_offset_y
            self.update_waypoint_source_position(waypoint, world_x, world_z)
            self.update_display_waypoint_position(waypoint, world_x, world_z)

        self.overlay_cache_key = None
        self.needs_redraw = True

    def select_waypoints_in_box(self) -> None:
        x1 = min(self.selection_box_start_map[0], self.selection_box_current_map[0])
        y1 = min(self.selection_box_start_map[1], self.selection_box_current_map[1])
        x2 = max(self.selection_box_start_map[0], self.selection_box_current_map[0])
        y2 = max(self.selection_box_start_map[1], self.selection_box_current_map[1])

        selected = set(self.selected_waypoint_ids) if self.selection_box_append else set()
        primary_id: int | None = None
        for waypoint in self.get_selectable_waypoints(margin_px=0.0):
            if x1 <= waypoint["map_x"] <= x2 and y1 <= waypoint["map_y"] <= y2:
                selected.add(waypoint["id"])
                primary_id = waypoint["id"]

        self.update_selection_state(selected, primary_id=primary_id)

    def update_waypoint_source_position(self, waypoint: dict, world_x: float, world_z: float) -> None:
        source_list = self.generated_raw_waypoints if waypoint["source"] == "generated" else self.raw_waypoints
        source_id = waypoint["source_id"]
        if source_id >= len(source_list):
            return

        target = source_list[source_id]
        pos = target.setdefault("pos", {})
        pos["x"] = float(world_x)
        pos["z"] = float(world_z)
        pos.setdefault("y", 70.0)

    def update_display_waypoint_position(self, waypoint: dict, world_x: float, world_z: float) -> None:
        old_chunk = (waypoint["tile_x"], waypoint["tile_z"])
        waypoint["pos"]["x"] = float(world_x)
        waypoint["pos"]["z"] = float(world_z)
        waypoint["map_x"], waypoint["map_y"] = self.waypoint_to_map_px(waypoint)
        waypoint["tile_x"] = int(math.floor(waypoint["pos"]["x"] / self.tile_size))
        waypoint["tile_z"] = int(math.floor(waypoint["pos"]["z"] / self.tile_size))
        new_chunk = (waypoint["tile_x"], waypoint["tile_z"])
        if new_chunk != old_chunk:
            old_bucket = self.waypoint_chunks.get(old_chunk, [])
            self.waypoint_chunks[old_chunk] = [item for item in old_bucket if item["id"] != waypoint["id"]]
            self.waypoint_chunks.setdefault(new_chunk, []).append(waypoint)

    def move_selected_waypoint_to_map(self, map_x: float, map_y: float) -> None:
        if self.selected_waypoint_id is None or self.active_map is None:
            return
        if self.selected_waypoint_id >= len(self.display_waypoints):
            return

        waypoint = self.display_waypoints[self.selected_waypoint_id]
        world_x = map_x + self.active_map.min_x * self.tile_size
        world_z = map_y + self.active_map.min_z * self.tile_size
        self.update_waypoint_source_position(waypoint, world_x, world_z)
        self.update_display_waypoint_position(waypoint, world_x, world_z)
        self.overlay_cache_key = None
        self.needs_redraw = True

    def refresh_waypoint_list(self) -> None:
        list_note = self.t("markers_count", count=len(self.display_waypoints))
        if self.generated_raw_waypoints:
            list_note += f" | {self.t('markers_generated_suffix', count=len(self.generated_raw_waypoints))}"
        dpg.set_value("waypoint_count_text", list_note)
        self.refresh_selected_waypoint_editor()

        if not dpg.does_item_exist("waypoint_list"):
            return

        dpg.delete_item("waypoint_list", children_only=True)
        waypoints_to_render = self.display_waypoints[:MAX_WAYPOINT_LIST_ITEMS]
        if self.selected_waypoint_id is not None and self.selected_waypoint_id < len(self.display_waypoints):
            selected = self.display_waypoints[self.selected_waypoint_id]
            if selected["id"] >= MAX_WAYPOINT_LIST_ITEMS:
                waypoints_to_render = [selected, *waypoints_to_render[:-1]]

        for waypoint in waypoints_to_render:
            prefix = ">" if waypoint["id"] in self.selected_waypoint_ids else " "
            label = (
                f"{prefix} {waypoint['name']} "
                f"[{waypoint['iconName']}] "
                f"x={waypoint['pos']['x']:.1f} z={waypoint['pos']['z']:.1f}"
            )
            dpg.add_selectable(
                label=label,
                default_value=waypoint["id"] in self.selected_waypoint_ids,
                callback=self.on_waypoint_selected,
                user_data=waypoint["id"],
                parent="waypoint_list",
            )

        if len(self.display_waypoints) > len(waypoints_to_render):
            list_note += f" | {self.t('markers_first_shown', count=len(waypoints_to_render))}"
            dpg.set_value("waypoint_count_text", list_note)
        dpg.configure_item("waypoint_list", show=self.show_waypoint_list)

    def waypoint_to_map_px(self, waypoint: dict) -> tuple[float, float]:
        if self.active_map is None:
            return 0.0, 0.0
        map_x = waypoint["pos"]["x"] - self.active_map.min_x * self.tile_size
        map_y = waypoint["pos"]["z"] - self.active_map.min_z * self.tile_size
        return map_x, map_y

    def map_to_screen(self, map_x: float, map_y: float) -> tuple[float, float]:
        viewer_w, viewer_h = self.get_viewer_size()
        screen_x = (map_x - self.camera_x) * self.scale + viewer_w / 2.0
        screen_y = (map_y - self.camera_y) * self.scale + viewer_h / 2.0
        return screen_x, screen_y

    def screen_to_map(self, screen_x: float, screen_y: float) -> tuple[float, float]:
        viewer_w, viewer_h = self.get_viewer_size()
        map_x = self.camera_x + (screen_x - viewer_w / 2.0) / self.scale
        map_y = self.camera_y + (screen_y - viewer_h / 2.0) / self.scale
        return map_x, map_y

    def get_viewer_size(self) -> tuple[int, int]:
        width, height = dpg.get_item_rect_size("viewer_panel")
        return max(int(width), 0), max(int(height), 0)

    def get_viewer_rect_min(self) -> tuple[float, float] | None:
        target = "map_drawlist" if dpg.does_item_exist("map_drawlist") else "viewer_panel"
        if not dpg.does_item_exist(target):
            return None
        state = dpg.get_item_state(target)
        rect_min = state.get("rect_min")
        if rect_min is None:
            return None
        return float(rect_min[0]), float(rect_min[1])

    def get_item_rect_min(self, tag: str) -> tuple[float, float] | None:
        if not dpg.does_item_exist(tag):
            return None
        state = dpg.get_item_state(tag)
        rect_min = state.get("rect_min")
        if rect_min is None:
            return None
        return float(rect_min[0]), float(rect_min[1])

    def item_rect_contains(self, tag: str, mouse_pos: tuple[float, float] | None = None) -> bool:
        if not dpg.does_item_exist(tag):
            return False
        rect_min = self.get_item_rect_min(tag)
        if rect_min is None:
            return False
        width, height = dpg.get_item_rect_size(tag)
        if width <= 0 or height <= 0:
            return False
        mouse_x, mouse_y = mouse_pos if mouse_pos is not None else dpg.get_mouse_pos(local=False)
        return (
            rect_min[0] <= mouse_x <= rect_min[0] + float(width)
            and rect_min[1] <= mouse_y <= rect_min[1] + float(height)
        )

    def get_mouse_local_to_viewer(self) -> tuple[float, float] | None:
        mouse_x, mouse_y = dpg.get_mouse_pos(local=False)
        rect_min = self.get_viewer_rect_min()
        if rect_min is None:
            return None
        rect_x, rect_y = rect_min
        return mouse_x - rect_x, mouse_y - rect_y

    def viewer_hovered(self) -> bool:
        drawlist_hovered = dpg.does_item_exist("map_drawlist") and dpg.is_item_hovered("map_drawlist")
        panel_hovered = dpg.does_item_exist("viewer_panel") and dpg.is_item_hovered("viewer_panel")
        return bool(drawlist_hovered or panel_hovered)

    def process_sidebar_resize(self) -> bool:
        if not self.sidebar_visible:
            self.sidebar_resize_active = False
            return False
        if not dpg.does_item_exist("sidebar") or not dpg.does_item_exist("sidebar_resize_grip"):
            self.sidebar_resize_active = False
            return False

        mouse_pos = dpg.get_mouse_pos(local=False)
        hovered = self.item_rect_contains("sidebar_resize_grip", mouse_pos)
        left_down = dpg.is_mouse_button_down(0)
        mouse_x, _ = mouse_pos

        if left_down:
            if not self.sidebar_resize_active and hovered:
                self.sidebar_resize_active = True
            if self.sidebar_resize_active:
                rect_min = self.get_item_rect_min("sidebar")
                if rect_min is not None:
                    self.apply_sidebar_width(mouse_x - rect_min[0], persist=False)
                return True
        elif self.sidebar_resize_active:
            self.sidebar_resize_active = False
            self.apply_sidebar_width(self.ui_config["sidebar_width"], persist=True)
            return True

        return hovered

    def mark_interaction(self, frames: int = INTERACTION_GRACE_FRAMES) -> None:
        self.interaction_active_until_frame = max(
            self.interaction_active_until_frame,
            self.frame_index + frames,
        )

    def is_interacting(self) -> bool:
        return self.frame_index < self.interaction_active_until_frame

    def zoom_at_cursor(self, wheel_delta: float) -> None:
        if self.active_map is None or not self.viewer_hovered():
            return

        old_scale = self.scale
        factor = math.exp(wheel_delta * 0.14)
        self.scale = self.clamp_map_scale(self.scale * factor)
        if abs(self.scale - old_scale) < 1e-6:
            return

        local_pos = self.get_mouse_local_to_viewer()
        if local_pos is None:
            return
        local_x, local_y = local_pos
        map_x, map_y = self.screen_to_map(local_x, local_y)
        viewer_w, viewer_h = self.get_viewer_size()
        self.camera_x = map_x - (local_x - viewer_w / 2.0) / self.scale
        self.camera_y = map_y - (local_y - viewer_h / 2.0) / self.scale
        self.mark_interaction()
        self.overlay_cache_key = None
        dpg.set_value("zoom_text", f"Zoom: {self.scale:.3f}x")
        self.needs_redraw = True

    def on_mouse_wheel(self, sender, app_data, user_data=None) -> None:
        self.zoom_at_cursor(float(app_data))

    def on_key_press(self, sender, app_data, user_data=None) -> None:
        if app_data == dpg.mvKey_Delete:
            if self.image_preview_bounds_map is not None and (
                self.image_preview_selected or not self.selected_waypoint_ids
            ):
                self.remove_loaded_image()
            else:
                self.delete_selected_waypoint()
            return

        if app_data == dpg.mvKey_H:
            self.sidebar_visible = not self.sidebar_visible
            if dpg.does_item_exist("sidebar"):
                dpg.configure_item("sidebar", show=self.sidebar_visible)
            if dpg.does_item_exist("sidebar_resize_grip"):
                dpg.configure_item("sidebar_resize_grip", show=self.sidebar_visible)
            return

        ctrl_down = (
            dpg.is_key_down(dpg.mvKey_LControl)
            or dpg.is_key_down(dpg.mvKey_RControl)
        )
        if not ctrl_down:
            return

        if app_data == dpg.mvKey_Z:
            if self.is_shift_pressed():
                self.redo()
            else:
                self.undo()
        elif app_data == dpg.mvKey_Y:
            self.redo()
        elif app_data == dpg.mvKey_S:
            self.save_waypoints()

    def process_mouse(self) -> None:
        if not dpg.does_item_exist("viewer_panel"):
            return

        if self.process_sidebar_resize():
            return

        mouse_x, mouse_y = dpg.get_mouse_pos(local=False)
        hovered = self.viewer_hovered()
        local_pos = self.get_mouse_local_to_viewer()

        if dpg.is_mouse_button_down(1):
            if not self.right_dragging and hovered:
                self.right_dragging = True
                self.right_drag_last = (mouse_x, mouse_y)
            elif self.right_dragging:
                dx = mouse_x - self.right_drag_last[0]
                dy = mouse_y - self.right_drag_last[1]
                self.right_drag_last = (mouse_x, mouse_y)
                self.camera_x -= dx / self.scale
                self.camera_y -= dy / self.scale
                self.mark_interaction()
                self.overlay_cache_key = None
                self.needs_redraw = True
        else:
            self.right_dragging = False

        if dpg.is_mouse_button_down(0):
            if not self.left_pressed and hovered:
                self.left_pressed = True
                self.left_pressed_in_viewer = True
                self.left_press_pos = (mouse_x, mouse_y)
                if local_pos is not None:
                    map_x, map_y = self.screen_to_map(local_pos[0], local_pos[1])
                    preview_hit = self.hit_test_image_preview(local_pos[0], local_pos[1])
                    if preview_hit is not None:
                        self.push_undo_state()
                        self.image_preview_selected = True
                        self.image_preview_drag_mode = preview_hit
                        self.image_preview_drag_start_map = (map_x, map_y)
                        self.image_preview_drag_initial_bounds = self.image_preview_bounds_map
                        self.selection_box_active = False
                        self.selection_drag_active = False
                        self.needs_redraw = True
                        return

                    self.image_preview_selected = False
                    hit_id = self.find_waypoint_at(local_pos[0], local_pos[1])
                    if hit_id is not None and hit_id in self.selected_waypoint_ids:
                        self.push_undo_state()
                        self.selection_drag_active = True
                        self.selection_drag_start_map = (map_x, map_y)
                        self.build_selection_snapshot()
                    else:
                        self.selection_drag_active = False
                        self.selection_box_active = True
                        self.selection_box_start_map = (map_x, map_y)
                        self.selection_box_current_map = (map_x, map_y)
                        self.selection_box_append = self.is_shift_pressed()
                        if not self.selection_box_append:
                            self.update_selection_state(set())
                        else:
                            self.overlay_cache_key = None
                            self.needs_redraw = True
            elif self.left_pressed and local_pos is not None:
                map_x, map_y = self.screen_to_map(local_pos[0], local_pos[1])
                if self.image_preview_drag_mode is not None:
                    self.mark_interaction()
                    self.update_image_preview_transform(map_x, map_y)
                elif self.selection_drag_active:
                    self.mark_interaction()
                    delta_map_x = map_x - self.selection_drag_start_map[0]
                    delta_map_y = map_y - self.selection_drag_start_map[1]
                    self.apply_selection_move(delta_map_x, delta_map_y)
                elif self.selection_box_active:
                    self.mark_interaction()
                    self.selection_box_current_map = (map_x, map_y)
                    self.overlay_cache_key = None
                    self.needs_redraw = True
        else:
            if self.left_pressed and self.left_pressed_in_viewer:
                if self.image_preview_drag_mode is not None:
                    self.flush_image_marker_preview_refresh()
                    self.needs_redraw = True
                elif self.selection_box_active:
                    click_distance = math.hypot(
                        mouse_x - self.left_press_pos[0],
                        mouse_y - self.left_press_pos[1],
                    )
                    if click_distance < SELECTION_CLICK_TOLERANCE_SCREEN_PX:
                        hit_id = None
                        if local_pos is not None:
                            hit_id = self.find_waypoint_at(local_pos[0], local_pos[1])
                        selected = set(self.selected_waypoint_ids) if self.selection_box_append else set()
                        if hit_id is not None:
                            selected.add(hit_id)
                            self.update_selection_state(selected, primary_id=hit_id)
                        elif not self.selection_box_append:
                            self.update_selection_state(set())
                    else:
                        self.select_waypoints_in_box()
                elif self.selection_drag_active:
                    self.refresh_waypoint_list()
                    self.needs_redraw = True

            self.selection_box_active = False
            self.selection_box_append = False
            self.selection_drag_active = False
            self.selection_drag_snapshot = []
            self.image_preview_drag_mode = None
            self.image_preview_drag_initial_bounds = None
            self.left_pressed = False
            self.left_pressed_in_viewer = False
            self.dragging_waypoint_id = None

    def select_waypoint_at(self, local_x: float, local_y: float) -> None:
        waypoint_id = self.find_waypoint_at(local_x, local_y)
        if waypoint_id is None:
            self.update_selection_state(set())
            return
        self.update_selection_state({waypoint_id}, primary_id=waypoint_id)

    def process_tile_queue(self) -> None:
        if self.active_map is None:
            return
        self.visible_tile_targets = self.get_visible_chunk_keys()
        self.cached_tile_targets = set(self.visible_tile_targets)
        self.effective_tile_cache_limit = len(self.tile_textures)
        self.set_progress(f"Зоны в памяти: {len(self.tile_textures)} / {len(self.active_map.zones)}")

    def visible_map_rect(self) -> tuple[float, float, float, float]:
        viewer_w, viewer_h = self.get_viewer_size()
        left = self.camera_x - viewer_w / (2.0 * self.scale)
        top = self.camera_y - viewer_h / (2.0 * self.scale)
        right = self.camera_x + viewer_w / (2.0 * self.scale)
        bottom = self.camera_y + viewer_h / (2.0 * self.scale)
        return left, top, right, bottom

    def compute_tile_targets(self, margin_chunks: int) -> list[tuple[int, int]]:
        if self.active_map is None:
            return []

        left, top, right, bottom = self.visible_map_rect()
        min_tx = int(math.floor(left / self.tile_size)) - margin_chunks
        max_tx = int(math.floor(right / self.tile_size)) + margin_chunks
        min_tz = int(math.floor(top / self.tile_size)) - margin_chunks
        max_tz = int(math.floor(bottom / self.tile_size)) + margin_chunks

        center_tx = self.camera_x / self.tile_size
        center_tz = self.camera_y / self.tile_size
        targets: list[tuple[int, int]] = []

        for local_x in range(min_tx, max_tx + 1):
            tile_x = local_x + self.active_map.min_x
            for local_z in range(min_tz, max_tz + 1):
                tile_z = local_z + self.active_map.min_z
                key = (tile_x, tile_z)
                if key not in self.active_map.tiles:
                    continue
                targets.append(key)

        targets.sort(key=lambda item: (item[0] - self.active_map.min_x - center_tx) ** 2 + (item[1] - self.active_map.min_z - center_tz) ** 2)
        return targets

    def unload_tile_texture(self, key: tuple[int, int]) -> None:
        texture = self.tile_textures.pop(key, None)
        self.tile_last_used.pop(key, None)
        self.zone_reveal_progress.pop(key, None)
        self.zone_reveal_direction.pop(key, None)
        self.zone_disable_pending.discard(key)
        if texture is None:
            return
        if texture.tag in self.tile_texture_tags:
            self.tile_texture_tags.remove(texture.tag)
        if dpg.does_item_exist(texture.tag):
            dpg.delete_item(texture.tag)

    def trim_tile_cache(self) -> None:
        overflow = len(self.tile_textures) - self.effective_tile_cache_limit
        if overflow <= 0:
            return

        candidates = sorted(
            self.tile_textures.keys(),
            key=lambda key: (
                key in self.cached_tile_targets,
                key in self.visible_tile_targets,
                self.tile_last_used.get(key, -1),
            ),
        )
        for key in candidates:
            if overflow <= 0:
                break
            if key in self.cached_tile_targets and len(self.tile_textures) <= self.effective_tile_cache_limit:
                break
            self.unload_tile_texture(key)
            overflow -= 1

    def get_visible_waypoints(self, margin_px: float = 128.0) -> list[dict]:
        if not self.display_waypoints:
            self.last_visible_waypoint_count = 0
            return []

        left, top, right, bottom = self.visible_map_rect()
        left -= margin_px
        top -= margin_px
        right += margin_px
        bottom += margin_px
        visible: list[dict] = []
        allowed_chunks = self.get_visible_chunk_keys(margin_px=margin_px)

        for chunk_key in allowed_chunks:
            chunk_waypoints = self.waypoint_chunks.get(chunk_key, [])
            if not chunk_waypoints:
                continue

            for waypoint in chunk_waypoints:
                if not self.is_waypoint_visible_by_layers(waypoint):
                    continue
                if left <= waypoint["map_x"] <= right and top <= waypoint["map_y"] <= bottom:
                    visible.append(waypoint)

        self.last_visible_waypoint_count = len(visible)
        return visible

    def build_points_overlay(
        self,
        visible_waypoints: list[dict],
        viewer_w: int,
        viewer_h: int,
    ) -> tuple[str, tuple[float, float] | None]:
        interacting = self.is_interacting()
        if interacting:
            downscale = max(POINT_OVERLAY_DOWNSCALE_HEAVY, 5)
        else:
            downscale = POINT_OVERLAY_DOWNSCALE_HEAVY if len(visible_waypoints) > 12000 else POINT_OVERLAY_DOWNSCALE
        overlay_w = max(1, viewer_w // downscale)
        overlay_h = max(1, viewer_h // downscale)
        point_budget = INTERACTION_POINT_BUDGET if interacting else MAX_VISIBLE_POINT_MARKERS
        if len(visible_waypoints) > point_budget:
            step = max(1, len(visible_waypoints) // point_budget)
            visible_waypoints = visible_waypoints[::step]
        cache_key = (
            overlay_w,
            overlay_h,
            round(self.scale, 4),
            round(self.camera_x, 1),
            round(self.camera_y, 1),
            len(visible_waypoints),
            self.selected_waypoint_id,
            interacting,
        )

        selected_screen: tuple[float, float] | None = None
        if self.overlay_cache_key != cache_key:
            pixels = np.zeros((overlay_h, overlay_w, 4), dtype=np.uint8)
            point_radius = 1 if interacting or self.scale < 0.16 else 2
            occupied: set[tuple[int, int]] = set()

            for waypoint in visible_waypoints:
                screen_x, screen_y = self.map_to_screen(waypoint["map_x"], waypoint["map_y"])
                px = int(screen_x / downscale)
                py = int(screen_y / downscale)
                if px < 0 or py < 0 or px >= overlay_w or py >= overlay_h:
                    continue

                if waypoint["id"] == self.selected_waypoint_id:
                    selected_screen = (screen_x, screen_y)

                cell = (px, py)
                if interacting and cell in occupied and waypoint["id"] != self.selected_waypoint_id:
                    continue
                occupied.add(cell)

                tint = (
                    waypoint["color"]["r"],
                    waypoint["color"]["g"],
                    waypoint["color"]["b"],
                    max(waypoint["color"]["a"], 180),
                )
                r, g, b, a = [max(0, min(255, int(v))) for v in tint]

                x1 = max(0, px - point_radius)
                x2 = min(overlay_w, px + point_radius + 1)
                y1 = max(0, py - point_radius)
                y2 = min(overlay_h, py + point_radius + 1)
                pixels[y1:y2, x1:x2, 0] = r
                pixels[y1:y2, x1:x2, 1] = g
                pixels[y1:y2, x1:x2, 2] = b
                pixels[y1:y2, x1:x2, 3] = a

            texture_data = pixels.astype(np.float32).ravel() / 255.0
            self.update_overlay_texture(overlay_w, overlay_h, texture_data)
            self.overlay_cache_key = cache_key
            self.overlay_selected_screen = selected_screen
        else:
            selected_screen = self.overlay_selected_screen

        return self.overlay_texture_tag, selected_screen

    def draw_selection_overlay(self, draw_tag: str) -> None:
        viewer_w, viewer_h = self.get_viewer_size()
        for waypoint_id in sorted(self.selected_waypoint_ids):
            if waypoint_id < 0 or waypoint_id >= len(self.display_waypoints):
                continue
            waypoint = self.display_waypoints[waypoint_id]
            screen_x, screen_y = self.map_to_screen(waypoint["map_x"], waypoint["map_y"])
            if screen_x < -48 or screen_y < -48 or screen_x > viewer_w + 48 or screen_y > viewer_h + 48:
                continue
            icon = self.icon_textures.get(waypoint["iconIndex"], self.icon_textures.get(0))
            base_size = icon.width if icon else 18
            marker_size = self.get_waypoint_marker_size(base_size)
            dpg.draw_circle(
                (screen_x, screen_y),
                radius=max(10.0, marker_size * 0.68),
                color=(116, 228, 255, 245),
                thickness=2.0,
                parent=draw_tag,
            )

        if self.selection_box_active:
            x1, y1 = self.map_to_screen(self.selection_box_start_map[0], self.selection_box_start_map[1])
            x2, y2 = self.map_to_screen(self.selection_box_current_map[0], self.selection_box_current_map[1])
            dpg.draw_rectangle(
                (min(x1, x2), min(y1, y2)),
                (max(x1, x2), max(y1, y2)),
                color=(130, 235, 255, 255),
                fill=(95, 190, 255, 82),
                thickness=2.5,
                parent=draw_tag,
            )

    def draw_grid(self, draw_tag: str) -> None:
        if self.active_map is None or self.scale < 0.08:
            return

        left, top, right, bottom = self.visible_map_rect()
        start_x = max(0, int(left // self.tile_size))
        end_x = min(self.active_map.max_x - self.active_map.min_x + 1, int(math.ceil(right / self.tile_size)))
        start_y = max(0, int(top // self.tile_size))
        end_y = min(self.active_map.max_z - self.active_map.min_z + 1, int(math.ceil(bottom / self.tile_size)))

        alpha = 220 if self.scale >= 0.2 else 170
        color = (92, 122, 156, alpha)
        thickness = 1.2 if self.scale >= 0.2 else 1.0
        map_w = (self.active_map.max_x - self.active_map.min_x + 1) * self.tile_size
        map_h = (self.active_map.max_z - self.active_map.min_z + 1) * self.tile_size

        for x in range(start_x, end_x + 1):
            sx, sy1 = self.map_to_screen(x * self.tile_size, 0.0)
            _, sy2 = self.map_to_screen(x * self.tile_size, map_h)
            dpg.draw_line((sx, sy1), (sx, sy2), color=color, thickness=thickness, parent=draw_tag)

        for y in range(start_y, end_y + 1):
            sx1, sy = self.map_to_screen(0.0, y * self.tile_size)
            sx2, _ = self.map_to_screen(map_w, y * self.tile_size)
            dpg.draw_line((sx1, sy), (sx2, sy), color=color, thickness=thickness, parent=draw_tag)

    def draw_tiles(self, draw_tag: str) -> None:
        left, top, right, bottom = self.visible_map_rect()
        for key, texture in self.tile_textures.items():
            x1 = texture.map_x
            y1 = texture.map_y
            x2 = x1 + texture.width
            y2 = y1 + texture.height
            if x2 < left or y2 < top or x1 > right or y1 > bottom:
                continue

            sx1, sy1 = self.map_to_screen(x1, y1)
            sx2, sy2 = self.map_to_screen(x2, y2)
            self.tile_last_used[key] = self.frame_index
            reveal_progress = self.zone_reveal_progress.get(key, 1.0)
            if reveal_progress < 1.0:
                partial_sx2 = sx1 + (sx2 - sx1) * reveal_progress
                dpg.draw_image(
                    texture.tag,
                    (sx1, sy1),
                    (partial_sx2, sy2),
                    uv_min=(0.0, 0.0),
                    uv_max=(reveal_progress, 1.0),
                    parent=draw_tag,
                )
            else:
                dpg.draw_image(texture.tag, (sx1, sy1), (sx2, sy2), parent=draw_tag)

    def draw_image_preview(self, draw_tag: str) -> None:
        if self.image_preview_bounds_map is None:
            return

        x1, y1, x2, y2 = self.image_preview_bounds_map
        sx1, sy1 = self.map_to_screen(x1, y1)
        sx2, sy2 = self.map_to_screen(x2, y2)
        rect_min = (min(sx1, sx2), min(sy1, sy2))
        rect_max = (max(sx1, sx2), max(sy1, sy2))
        dpg.draw_rectangle(
            rect_min,
            rect_max,
            fill=(35, 46, 64, 105),
            color=(55, 75, 105, 160),
            thickness=1.0,
            parent=draw_tag,
        )

        preview_pixels, target_w, target_h = self.get_marker_preview_data()
        if target_w > 0 and target_h > 0 and preview_pixels:
            draw_radius = (
                float(self.ui_config["preview_point_radius_small"])
                if self.scale < 0.2
                else float(self.ui_config["preview_point_radius_big"])
            )
            draw_alpha = int(self.ui_config["preview_point_alpha"])
            map_w = max(1.0, x2 - x1)
            map_h = max(1.0, y2 - y1)
            for px, py, r, g, b in preview_pixels:
                u = (px + 0.5) / target_w
                v = (py + 0.5) / target_h
                map_x = x1 + u * map_w
                map_y = y1 + v * map_h
                point_sx, point_sy = self.map_to_screen(map_x, map_y)
                dpg.draw_circle(
                    (point_sx, point_sy),
                    radius=draw_radius,
                    fill=(r, g, b, draw_alpha),
                    color=(r, g, b, draw_alpha),
                    thickness=1.0,
                    parent=draw_tag,
                )

        border_color = (255, 204, 120, 255) if self.image_preview_selected else (120, 185, 255, 220)
        dpg.draw_rectangle(
            rect_min,
            rect_max,
            color=border_color,
            thickness=2.0,
            parent=draw_tag,
        )

        if self.image_preview_selected:
            handle_half = IMAGE_PREVIEW_HANDLE_SCREEN_PX * 0.5
            corners = [
                (rect_min[0], rect_min[1]),
                (rect_max[0], rect_min[1]),
                (rect_min[0], rect_max[1]),
                (rect_max[0], rect_max[1]),
            ]
            for cx, cy in corners:
                dpg.draw_rectangle(
                    (cx - handle_half, cy - handle_half),
                    (cx + handle_half, cy + handle_half),
                    fill=(255, 204, 120, 255),
                    color=(30, 30, 30, 255),
                    thickness=1.0,
                    parent=draw_tag,
                )

    def draw_waypoints(self, draw_tag: str) -> None:
        if self.active_map is None:
            return

        viewer_w, viewer_h = self.get_viewer_size()
        visible_waypoints = self.get_visible_waypoints(margin_px=128.0)
        if not visible_waypoints:
            self.last_waypoint_render_mode = "none"
            return

        target_budget = self.max_markers_on_screen
        if self.is_interacting():
            target_budget = max(250, self.max_markers_on_screen // 2)
        if len(visible_waypoints) > target_budget:
            step = max(1, len(visible_waypoints) // target_budget)
            visible_waypoints = visible_waypoints[::step]

        render_as_points = len(visible_waypoints) > MAX_VISIBLE_POINT_MARKERS
        if render_as_points:
            step = max(1, len(visible_waypoints) // MAX_VISIBLE_POINT_MARKERS)
            visible_waypoints = visible_waypoints[::step]
        effective_icon_scale = self.scale * max(0.2, float(self.marker_zoom_multiplier))
        low_zoom_square_cutover = max(180, min(1400, self.square_render_threshold // 6))
        render_as_squares = not render_as_points and (
            len(visible_waypoints) >= self.square_render_threshold
            or (
                effective_icon_scale < WAYPOINT_ICON_SCALE_SWITCH
                and len(visible_waypoints) >= low_zoom_square_cutover
            )
        )

        if render_as_points:
            self.last_waypoint_render_mode = "points"
        elif render_as_squares:
            self.last_waypoint_render_mode = "squares"
        else:
            self.last_waypoint_render_mode = "icons"
        if render_as_points:
            overlay_tag, selected_screen = self.build_points_overlay(visible_waypoints, viewer_w, viewer_h)
            dpg.draw_image(overlay_tag, (0, 0), (viewer_w, viewer_h), parent=draw_tag)
            if selected_screen is not None and self.selected_waypoint_id in self.selected_waypoint_ids:
                dpg.draw_circle(
                    selected_screen,
                    radius=10.0,
                    color=(255, 213, 74, 255),
                    thickness=2.0,
                    parent=draw_tag,
                )
            return

        for waypoint in visible_waypoints:
            map_x = waypoint["map_x"]
            map_y = waypoint["map_y"]
            screen_x, screen_y = self.map_to_screen(map_x, map_y)
            if screen_x < -64 or screen_y < -64 or screen_x > viewer_w + 64 or screen_y > viewer_h + 64:
                continue

            tint = (
                waypoint["color"]["r"],
                waypoint["color"]["g"],
                waypoint["color"]["b"],
                max(waypoint["color"]["a"], 180),
            )
            icon = self.icon_textures.get(waypoint["iconIndex"], self.icon_textures.get(0))
            if icon is None:
                continue

            marker_size = self.get_waypoint_marker_size(icon.width)
            x1 = screen_x - marker_size / 2.0
            y1 = screen_y - marker_size / 2.0
            x2 = screen_x + marker_size / 2.0
            y2 = screen_y + marker_size / 2.0
            if render_as_squares:
                square_size = max(3.0, min(marker_size * 0.42, 7.0))
                dpg.draw_rectangle(
                    (screen_x - square_size / 2.0, screen_y - square_size / 2.0),
                    (screen_x + square_size / 2.0, screen_y + square_size / 2.0),
                    fill=tint,
                    color=(0, 0, 0, 120),
                    thickness=1.0,
                    parent=draw_tag,
                )
            else:
                dpg.draw_image(icon.tag, (x1, y1), (x2, y2), color=tint, parent=draw_tag)

            if waypoint["id"] == self.selected_waypoint_id:
                dpg.draw_circle(
                    (screen_x, screen_y),
                    radius=max(10.0, marker_size * 0.65),
                    color=(255, 213, 74, 255),
                    thickness=2.0,
                    parent=draw_tag,
                )
                if effective_icon_scale >= WAYPOINT_HIDE_NAMES_SCALE:
                    dpg.draw_text(
                        (screen_x + 10, screen_y - 18),
                        waypoint["name"],
                        color=(255, 245, 200, 255),
                        size=16,
                        parent=draw_tag,
                    )

    def render_scene(self) -> None:
        if not dpg.does_item_exist("map_drawlist"):
            return

        viewer_w, viewer_h = self.get_viewer_size()
        if viewer_w <= 0 or viewer_h <= 0:
            return

        dpg.configure_item("map_drawlist", width=viewer_w, height=viewer_h)
        dpg.delete_item("map_drawlist", children_only=True)
        dpg.draw_rectangle(
            (0, 0),
            (viewer_w, viewer_h),
            fill=(16, 20, 28, 255),
            color=(16, 20, 28, 255),
            parent="map_drawlist",
        )

        if self.active_map is None:
            dpg.draw_text((20, 20), self.t("status_no_map_selected"), color=(220, 220, 220, 255), size=18, parent="map_drawlist")
            self.needs_redraw = False
            return

        self.draw_tiles("map_drawlist")
        self.draw_grid("map_drawlist")
        self.draw_image_preview("map_drawlist")
        self.draw_waypoints("map_drawlist")
        self.draw_selection_overlay("map_drawlist")

        total_tiles = len(self.active_map.zones)
        loaded_tiles = len(self.tile_textures)
        footer = self.t(
            "footer",
            map_id=self.active_map.map_id,
            loaded=loaded_tiles,
            total=total_tiles,
            all_count=len(self.display_waypoints),
            visible_count=self.last_visible_waypoint_count,
            mode=self.t(f"render_mode_{self.last_waypoint_render_mode}",) if self.last_waypoint_render_mode in {"none", "icons", "squares", "points"} else self.last_waypoint_render_mode,
            interactive=self.t("interactive_on") if self.is_interacting() else self.t("interactive_off"),
        )
        dpg.draw_text((12, viewer_h - 28), footer, color=(235, 235, 235, 255), size=15, parent="map_drawlist")
        self.needs_redraw = False

    def create_ui(self) -> None:
        dpg.create_context()
        with dpg.texture_registry(tag="texture_registry"):
            pass

        with dpg.window(tag="main_window", label="Waypoint Editor"):
            with dpg.group(horizontal=True):
                with dpg.child_window(tag="sidebar", width=int(self.ui_config["sidebar_width"]), border=True):

                    with dpg.tab_bar(tag="sidebar_tabs"):
                        with dpg.tab(label="Main"):
                            dpg.add_text("Карта", color=(255, 221, 120))
                            dpg.add_text("", tag="map_name_text")
                            dpg.add_button(label="Fit To Map", width=-1, callback=self.on_fit_clicked)
                            dpg.add_button(label="Enable All Regions", width=-1, callback=lambda *_: self.enable_all_zones())
                            dpg.add_button(label="Disable All Regions", width=-1, callback=lambda *_: self.disable_all_zones())
                            with dpg.child_window(tag="zone_filter_list", height=220, border=True):
                                pass

                        with dpg.tab(label="Image"):
                            dpg.add_text("Картинка -> метки", color=(255, 221, 120))
                            dpg.add_input_text(tag="image_path_input", width=-1, readonly=True, default_value="")
                            dpg.add_button(label="Open Image...", width=-1, callback=self.on_open_image_clicked)
                            dpg.add_text("Превью маркеров обновляется при изменении рамки и параметров.", wrap=320)
                            dpg.add_text("Max markers")
                            dpg.add_input_int(
                                tag="image_marker_limit_input",
                                default_value=DEFAULT_MAX_GENERATED_MARKERS,
                                min_value=1,
                                min_clamped=True,
                                width=-1,
                                callback=self.on_image_settings_changed,
                            )
                            dpg.add_text("Превью маркеров: -", tag="image_marker_estimate_text")
                            dpg.add_checkbox(
                                label="Генерировать с фоном (включая прозрачный)",
                                tag="image_include_background_input",
                                default_value=False,
                                callback=self.on_image_settings_changed,
                            )
                            dpg.add_text("Отсечение по прозрачности", tag="image_alpha_cutoff_label")
                            dpg.add_slider_int(
                                tag="image_alpha_cutoff_input",
                                default_value=DEFAULT_ALPHA_CUTOFF,
                                min_value=0,
                                max_value=255,
                                width=-1,
                                callback=self.on_image_settings_changed,
                            )
                            dpg.add_text("Шаг сетки отсечения (px)")
                            dpg.add_input_int(
                                tag="image_sampling_step_input",
                                default_value=1,
                                min_value=1,
                                min_clamped=True,
                                width=-1,
                                callback=self.on_image_settings_changed,
                            )
                            dpg.add_checkbox(
                                label="Только контур",
                                tag="image_contour_only_input",
                                default_value=False,
                                callback=self.on_image_settings_changed,
                            )
                            dpg.add_text("Отсечение по яркости", tag="image_brightness_cutoff_label")
                            dpg.add_slider_int(
                                tag="image_brightness_cutoff_input",
                                default_value=DEFAULT_BRIGHTNESS_CUTOFF,
                                min_value=0,
                                max_value=255,
                                width=-1,
                                callback=self.on_image_settings_changed,
                            )
                            dpg.add_text("Толщина контура", tag="image_contour_thickness_label")
                            dpg.add_input_int(
                                tag="image_contour_thickness_input",
                                default_value=DEFAULT_CONTOUR_THICKNESS,
                                min_value=1,
                                min_clamped=True,
                                width=-1,
                                callback=self.on_image_settings_changed,
                            )
                            dpg.add_text("Эти параметры влияют только на режим контура.", tag="image_contour_help_text", wrap=320)
                            dpg.add_text("Icon")
                            dpg.add_slider_int(tag="image_icon_input", default_value=0, min_value=0, max_value=6, width=-1)
                            dpg.add_checkbox(label="Auto icons", tag="image_auto_icons_input", default_value=True)
                            dpg.add_button(label="Generate From Image", width=-1, callback=self.on_generate_image_clicked)
                            dpg.add_button(label="Clear Generated", width=-1, callback=self.on_clear_generated_clicked)
                            dpg.add_button(label="Bake Generated", width=-1, callback=self.on_bake_generated_clicked)
                            dpg.add_text("Буфер генерации пуст", tag="generated_status", wrap=320)

                        with dpg.tab(label="Layers"):
                            dpg.add_text("Редактор слоёв", color=(255, 221, 120))
                            dpg.add_input_text(tag="layer_name_input", hint="Layer name", width=-1)
                            dpg.add_button(label="Add Selected To Layer", width=-1, callback=lambda *_: self.add_selection_to_layer())
                            dpg.add_text("Клик по слою выделяет его метки; чекбокс включает/скрывает слой.", wrap=320)
                            with dpg.child_window(tag="layers_list", height=260, border=True):
                                pass

                        with dpg.tab(label="Waypoints"):
                            dpg.add_text("Метки", color=(255, 221, 120))
                            dpg.add_text("Метки: 0", tag="waypoint_count_text")
                            dpg.add_button(label="Show waypoint list", tag="toggle_waypoint_list_button", width=-1, callback=self.on_toggle_waypoint_list_clicked)
                            dpg.add_button(label="Save changes", width=-1, callback=self.on_save_changes_clicked)
                            dpg.add_button(label="Center Selected", width=-1, callback=self.on_center_selected_clicked)
                            dpg.add_button(label="Delete Selected", width=-1, callback=self.on_delete_selected_clicked)
                            with dpg.child_window(tag="waypoint_list", height=340, border=True, show=self.show_waypoint_list):
                                pass

                        with dpg.tab(label="Settings"):
                            dpg.add_text("Оптимизация", color=(255, 221, 120))
                            dpg.add_text("Markers on screen")
                            dpg.add_input_int(tag="marker_screen_limit_input", default_value=self.max_markers_on_screen, min_value=1, min_clamped=True, width=-1)
                            dpg.add_text("Squares after")
                            dpg.add_input_int(tag="marker_square_threshold_input", default_value=self.square_render_threshold, min_value=1, min_clamped=True, width=-1)
                            dpg.add_button(label="Apply Optimization", width=-1, callback=self.on_apply_optimization_clicked)

                            dpg.add_spacer(height=8)
                            dpg.add_separator()
                            dpg.add_text("UI Customization", color=(255, 221, 120))
                            dpg.add_text("Sidebar width")
                            dpg.add_input_int(tag="ui_sidebar_width_input", default_value=int(self.ui_config["sidebar_width"]), min_value=260, min_clamped=True, width=-1)
                            dpg.add_text("Preview alpha")
                            dpg.add_slider_int(tag="ui_preview_alpha_input", default_value=int(self.ui_config["preview_point_alpha"]), min_value=20, max_value=255, width=-1)
                            dpg.add_text("Preview radius small")
                            dpg.add_slider_float(tag="ui_preview_radius_small_input", default_value=float(self.ui_config["preview_point_radius_small"]), min_value=0.6, max_value=4.0, width=-1)
                            dpg.add_text("Preview radius big")
                            dpg.add_slider_float(tag="ui_preview_radius_big_input", default_value=float(self.ui_config["preview_point_radius_big"]), min_value=0.8, max_value=8.0, width=-1)
                            dpg.add_text("Rounding")
                            dpg.add_slider_float(tag="ui_rounding_input", default_value=float(self.ui_config["ui_rounding"]), min_value=0.0, max_value=18.0, width=-1)
                            dpg.add_text("Background color")
                            dpg.add_color_edit(tag="ui_bg_color_input", default_value=self.ui_config["ui_bg_color"], alpha_bar=False, width=-1)
                            dpg.add_text("Panel color")
                            dpg.add_color_edit(tag="ui_panel_color_input", default_value=self.ui_config["ui_panel_color"], alpha_bar=False, width=-1)
                            dpg.add_text("Frame color")
                            dpg.add_color_edit(tag="ui_frame_color_input", default_value=self.ui_config["ui_frame_color"], alpha_bar=False, width=-1)
                            dpg.add_text("Accent color")
                            dpg.add_color_edit(tag="ui_accent_color_input", default_value=self.ui_config["ui_accent_color"], alpha_bar=False, width=-1)
                            dpg.add_button(label="Apply UI Theme", width=-1, callback=lambda *_: self.apply_ui_theme())
                            dpg.add_button(label="Save UI Config", width=-1, callback=lambda *_: self.save_ui_config())

                        with dpg.tab(label="Help"):
                            dpg.add_text("Помощь", color=(255, 221, 120))
                            dpg.add_text("Управление:")
                            dpg.add_text("ПКМ + drag: панорама")
                            dpg.add_text("Колесо: зум к курсору")
                            dpg.add_text("ЛКМ: рамка выделения / drag выбранных")
                            dpg.add_text("Delete: удалить выбранные метки")
                            dpg.add_text("Ctrl+Z / Ctrl+Y: undo / redo")
                            dpg.add_spacer(height=6)
                            dpg.add_text("Важное:")
                            dpg.add_text("`Generate From Image` кладет метки в generated-буфер.")
                            dpg.add_text("`Bake Generated` переносит буфер в основной список меток.")
                            dpg.add_text("Слои влияют на видимость меток на экране.")
                            dpg.add_text("UI-кастомизация сохраняется в ui_config.json.")

                    dpg.add_spacer(height=8)
                    dpg.add_separator()
                    dpg.add_text("Status: Ready", tag="status_text", wrap=320)
                    dpg.add_text("Загрузка тайлов: 0 / 0", tag="progress_text", wrap=320)
                    dpg.add_text("Zoom: 1.000x", tag="zoom_text")

                with dpg.child_window(tag="viewer_panel", width=-1, height=-1, border=False, no_scrollbar=True):
                    with dpg.drawlist(tag="map_drawlist", width=100, height=100):
                        pass

        with dpg.handler_registry():
            dpg.add_mouse_wheel_handler(callback=self.on_mouse_wheel)
            dpg.add_key_press_handler(callback=self.on_key_press)

        self.configure_image_settings_visibility()
        self.update_image_marker_estimate(None)

        dpg.create_viewport(title="Waypoint Editor", width=1440, height=900)
        self.setup_fonts()
        # Установка иконки для таскбара и топбара
        try:
            if hasattr(dpg, 'set_viewport_icon'):
                icon_path = str(RESOURCE_ROOT / "assets" / "app.ico")
                dpg.set_viewport_icon(icon_path)
        except:
            pass
        dpg.setup_dearpygui()
        dpg.show_viewport()
        # Установка иконки приложения через Windows API
        self.set_app_icon()
        dpg.set_primary_window("main_window", True)
        dpg.maximize_viewport()

    def bootstrap(self) -> None:
        self.load_icon_textures()
        self.refresh_map_combo()
        if self.exbo_setup_required:
            self.raw_waypoints = []
            self.generated_raw_waypoints = []
            self.sync_waypoints_from_raw()
            self.set_status(self.t("status_choose_exbo_for_cfg"))
        else:
            self.load_waypoints()
        default_map = self.choose_default_map()
        if default_map:
            self.select_map(default_map)
        else:
            self.set_status(self.t("status_no_maps"))

    def tick(self) -> None:
        self.frame_index += 1
        self.process_mouse()
        self.update_zone_reveal_animation()

        if self.zone_reload_pending:
            self.zone_reload_pending = False
            self.reload_zone_textures()

        size = self.get_viewer_size()
        if size != self.last_viewer_size:
            self.last_viewer_size = size
            self.overlay_cache_key = None
            self.needs_redraw = True
            if self.pending_fit:
                self.fit_to_map()

        if self.pending_fit and size[0] > 0 and size[1] > 0:
            self.fit_to_map()

        self.process_tile_queue()

        if self.needs_redraw:
            self.render_scene()

    def run(self) -> None:
        self.create_ui()
        self.bootstrap()
        while dpg.is_dearpygui_running():
            self.tick()
            dpg.render_dearpygui_frame()
        dpg.destroy_context()


for _mixin, _names in (
    (
        UIBuildMixin,
        (
            "load_ui_config",
            "save_ui_config",
            "apply_ui_theme",
            "create_ui",
        ),
    ),
    (
        ZoneLoadingMixin,
        (
            "refresh_map_combo",
            "clear_tile_textures",
            "refresh_zone_list",
            "reload_zone_textures",
            "enable_all_zones",
            "disable_all_zones",
            "on_zone_toggle",
            "get_active_map_bounds",
            "select_map",
            "process_tile_queue",
        ),
    ),
    (
        ImageGenerationMixin,
        (
            "invalidate_image_marker_preview",
            "update_image_marker_estimate",
            "configure_image_settings_visibility",
            "on_image_settings_changed",
            "clear_image_preview",
            "get_auto_image_resolution",
            "get_effective_max_markers",
            "build_image_mask",
            "extract_contour_mask",
            "collect_marker_pixels",
            "get_marker_preview_data",
            "prepare_marker_source_image",
            "reset_image_preview_bounds",
            "load_image_preview_texture",
            "get_image_preview_screen_rect",
            "hit_test_image_preview",
            "update_image_preview_transform",
            "apply_optimization_settings",
            "load_image_from_path",
            "generate_markers_from_image",
            "clear_generated_waypoints",
            "bake_generated_waypoints",
            "on_image_picked",
            "on_open_image_clicked",
            "on_generate_image_clicked",
            "on_clear_generated_clicked",
            "on_bake_generated_clicked",
            "draw_image_preview",
        ),
    ),
    (
        LayerEditorMixin,
        (
            "waypoint_layer_key",
            "cleanup_layers",
            "is_waypoint_visible_by_layers",
            "refresh_layers_list",
            "on_layer_visibility_changed",
            "select_layer_waypoints",
            "add_selection_to_layer",
        ),
    ),
):
    for _name in _names:
        setattr(SimpleMapperDesktopApp, _name, getattr(_mixin, _name))


if __name__ == "__main__":
    SimpleMapperDesktopApp().run()
