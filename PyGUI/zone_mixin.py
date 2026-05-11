from __future__ import annotations

import math

import dearpygui.dearpygui as dpg
from PIL import Image

from app_types import TextureInfo


class ZoneLoadingMixin:
    def refresh_map_combo(self) -> None:
        maps = sorted(self.core.get_maps().values(), key=lambda item: item.name.lower())
        items = [map_info.map_id for map_info in maps]
        default_value = items[0] if items else ""
        if "map" in items:
            default_value = "map"
        if dpg.does_item_exist("map_name_text"):
            dpg.set_value("map_name_text", default_value or self.t("status_no_maps"))

    def clear_tile_textures(self) -> None:
        for tag in self.tile_texture_tags:
            if not dpg.does_item_exist(tag):
                continue
            try:
                dpg.delete_item(tag)
            except Exception:
                pass
        self.tile_texture_tags.clear()
        self.tile_textures.clear()
        self.tile_last_used.clear()
        self.visible_tile_targets.clear()
        self.cached_tile_targets.clear()
        self.tile_queue.clear()
        self.overlay_cache_key = None
        self.zone_reveal_progress.clear()
        self.zone_reveal_direction.clear()
        self.zone_disable_pending.clear()

    def zone_intersects_view(self, zone, margin_tiles: int = 1) -> bool:
        if self.active_map is None:
            return False

        left, top, right, bottom = self.visible_map_rect()
        margin_px = max(0, margin_tiles) * self.tile_size
        left -= margin_px
        top -= margin_px
        right += margin_px
        bottom += margin_px

        zone_x1 = (zone.min_tx - self.active_map.min_x) * self.tile_size
        zone_y1 = (zone.min_tz - self.active_map.min_z) * self.tile_size
        zone_x2 = (zone.max_tx - self.active_map.min_x + 1) * self.tile_size
        zone_y2 = (zone.max_tz - self.active_map.min_z + 1) * self.tile_size
        return not (zone_x2 < left or zone_y2 < top or zone_x1 > right or zone_y1 > bottom)

    def get_visible_zone_indices(self, margin_tiles: int = 1) -> list[int]:
        if self.active_map is None:
            return []

        visible: list[tuple[int, float]] = []
        center_x = self.camera_x
        center_y = self.camera_y
        for index, zone in enumerate(self.active_map.zones):
            if zone.name not in self.enabled_zone_names:
                continue
            if not self.zone_intersects_view(zone, margin_tiles=margin_tiles):
                continue

            zone_center_x = (zone.min_tx - self.active_map.min_x) * self.tile_size + (zone.tiles_wide * self.tile_size) / 2.0
            zone_center_y = (zone.min_tz - self.active_map.min_z) * self.tile_size + (zone.tiles_high * self.tile_size) / 2.0
            distance = (zone_center_x - center_x) ** 2 + (zone_center_y - center_y) ** 2
            visible.append((index, distance))

        visible.sort(key=lambda item: item[1])
        return [index for index, _ in visible]

    def load_zone_texture_by_index(self, index: int) -> bool:
        if self.active_map is None:
            return False

        key = (index, 0)
        if key in self.tile_textures:
            self.tile_last_used[key] = self.frame_index
            if self.zone_reveal_direction.get(key) == -1:
                self.zone_disable_pending.discard(key)
                self.zone_reveal_direction[key] = 1
                self.zone_reveal_progress[key] = max(0.0, min(1.0, self.zone_reveal_progress.get(key, 1.0)))
                return True
            return False

        try:
            zone = self.active_map.zones[index]
        except IndexError:
            return False

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
                self.tile_textures[key] = TextureInfo(
                    tag=texture_tag,
                    width=rgba.width,
                    height=rgba.height,
                    map_x=(zone.min_tx - self.active_map.min_x) * self.tile_size,
                    map_y=(zone.min_tz - self.active_map.min_z) * self.tile_size,
                )
                self.tile_last_used[key] = self.frame_index
                self.zone_reveal_progress[key] = 0.0
                self.zone_reveal_direction[key] = 1
                self.zone_disable_pending.discard(key)
                return True
        except Exception as error:
            self.set_status(
                self.t(
                    "status_zone_load_error",
                    zone=self.get_zone_display_name(zone.name),
                    error=error,
                )
            )
            return False

    def update_zone_reveal_animation(self) -> None:
        if not self.zone_reveal_progress:
            return

        changed = False
        finished_loading: list[tuple[int, int]] = []
        finished_unloading: list[tuple[int, int]] = []
        for key, progress in list(self.zone_reveal_progress.items()):
            direction = self.zone_reveal_direction.get(key, 1)
            next_progress = max(0.0, min(1.0, progress + 0.08 * direction))
            if next_progress != progress:
                self.zone_reveal_progress[key] = next_progress
                changed = True
            if direction >= 0 and next_progress >= 1.0:
                finished_loading.append(key)
            elif direction < 0 and next_progress <= 0.0:
                finished_unloading.append(key)

        for key in finished_loading:
            self.zone_reveal_progress.pop(key, None)
            self.zone_reveal_direction.pop(key, None)

        for key in finished_unloading:
            self.unload_tile_texture(key)

        if changed:
            self.needs_redraw = True

    def refresh_zone_list(self) -> None:
        if not dpg.does_item_exist("zone_filter_list"):
            return
        dpg.delete_item("zone_filter_list", children_only=True)
        if self.active_map is None:
            return

        for zone in self.active_map.zones:
            dpg.add_checkbox(
                label=self.get_zone_display_name(zone.name),
                default_value=zone.name in self.enabled_zone_names,
                callback=self.on_zone_toggle,
                user_data=zone.name,
                parent="zone_filter_list",
            )

    def reload_zone_textures(self) -> None:
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
        zone_index = None
        if self.active_map is not None:
            for index, zone in enumerate(self.active_map.zones):
                if zone.name == zone_name:
                    zone_index = index
                    break

        if bool(app_data):
            self.enabled_zone_names.add(zone_name)
            if zone_index is not None:
                key = (zone_index, 0)
                if key in self.tile_textures:
                    self.zone_disable_pending.discard(key)
                    self.zone_reveal_direction[key] = 1
                    self.zone_reveal_progress[key] = max(0.0, min(1.0, self.zone_reveal_progress.get(key, 1.0)))
        else:
            self.enabled_zone_names.discard(zone_name)
            if zone_index is not None:
                key = (zone_index, 0)
                if key in self.tile_textures:
                    self.zone_disable_pending.add(key)
                    self.zone_reveal_progress[key] = max(0.0, min(1.0, self.zone_reveal_progress.get(key, 1.0)))
                    self.zone_reveal_direction[key] = -1
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

    def select_map(self, map_id: str) -> None:
        try:
            map_info = self.core.get_map(map_id)
        except KeyError as error:
            self.set_status(str(error))
            return

        self.active_map_id = map_id
        self.active_map = map_info
        self.clear_tile_textures()
        self.tile_queue.clear()

        first_zone = map_info.zones[0] if map_info.zones else None
        if first_zone is None:
            self.set_status(self.t("status_map_no_png_zones", map_id=map_id))
            return

        try:
            if first_zone.tiles_wide > 0:
                self.tile_size = max(1, round(first_zone.image_width / first_zone.tiles_wide))
            else:
                with Image.open(first_zone.png_path) as first_image:
                    self.tile_size = first_image.width
        except Exception as error:
            self.set_status(self.t("status_png_zone_read_error", error=error))
            self.tile_size = 512

        # Safe startup: nothing is enabled until the user explicitly chooses regions.
        self.enabled_zone_names = set()
        self.refresh_zone_list()

        min_tx, max_tx, min_tz, max_tz = self.get_active_map_bounds()
        map_w = (max_tx - min_tx + 1) * self.tile_size
        map_h = (max_tz - min_tz + 1) * self.tile_size
        self.camera_x = (min_tx - self.active_map.min_x) * self.tile_size + map_w / 2.0
        self.camera_y = (min_tz - self.active_map.min_z) * self.tile_size + map_h / 2.0
        self.scale = 0.05
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
        if dpg.does_item_exist("map_name_text"):
            dpg.set_value("map_name_text", map_info.map_id)
        if dpg.does_item_exist("zoom_text"):
            dpg.set_value("zoom_text", self.t("zoom_label", scale=self.scale))
        self.set_status(self.t("status_map_with_region_hint", map_id=map_info.map_id))
        self.process_tile_queue()

    def process_tile_queue(self) -> None:
        if self.active_map is None:
            return

        visible_indices = self.get_visible_zone_indices(margin_tiles=1)
        self.visible_tile_targets = {(index, 0) for index in visible_indices}
        self.cached_tile_targets = set(self.visible_tile_targets) | set(self.tile_textures.keys())
        changed = False

        for key in list(self.tile_textures):
            zone_index = key[0]
            zone_name = self.active_map.zones[zone_index].name if 0 <= zone_index < len(self.active_map.zones) else ""
            if zone_name not in self.enabled_zone_names and key not in self.zone_disable_pending:
                self.unload_tile_texture(key)
                changed = True

        for index in visible_indices:
            if self.load_zone_texture_by_index(index):
                changed = True

        self.effective_tile_cache_limit = len(self.tile_textures)
        enabled_total = len(self.enabled_zone_names)
        visible_total = len(self.visible_tile_targets)
        self.set_progress(
            self.t(
                "progress_zone_memory",
                loaded=len(self.tile_textures),
                visible=visible_total,
                enabled=enabled_total,
                total=len(self.active_map.zones),
            )
        )
        if changed:
            self.needs_redraw = True
