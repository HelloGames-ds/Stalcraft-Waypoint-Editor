from __future__ import annotations

import json

import dearpygui.dearpygui as dpg

from app_constants import PROJECT_ROOT


class LayerEditorMixin:
    def get_layers_path(self):
        return PROJECT_ROOT / "layers.json"

    def save_layers_state(self) -> None:
        path = self.get_layers_path()
        payload = {
            "layer_counter": int(self.layer_counter),
            "layer_visibility": {
                str(name): bool(value) for name, value in self.layer_visibility.items()
            },
            "marker_layers": {
                str(name): [[source, int(source_id)] for source, source_id in sorted(members)]
                for name, members in sorted(self.marker_layers.items())
            },
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_layers_state(self) -> None:
        path = self.get_layers_path()
        self.marker_layers = {}
        self.layer_visibility = {}
        self.layer_counter = 1
        if not path.exists():
            self.refresh_layers_list()
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            self.refresh_layers_list()
            return
        if not isinstance(payload, dict):
            self.refresh_layers_list()
            return

        raw_layers = payload.get("marker_layers", {})
        if isinstance(raw_layers, dict):
            for layer_name, members in raw_layers.items():
                if not isinstance(layer_name, str) or not isinstance(members, list):
                    continue
                normalized_members: set[tuple[str, int]] = set()
                for item in members:
                    if not isinstance(item, (list, tuple)) or len(item) != 2:
                        continue
                    source, source_id = item
                    try:
                        normalized_members.add((str(source), int(source_id)))
                    except Exception:
                        continue
                if normalized_members:
                    self.marker_layers[layer_name] = normalized_members

        raw_visibility = payload.get("layer_visibility", {})
        if isinstance(raw_visibility, dict):
            for layer_name, value in raw_visibility.items():
                if isinstance(layer_name, str):
                    self.layer_visibility[layer_name] = bool(value)

        try:
            self.layer_counter = max(1, int(payload.get("layer_counter", 1)))
        except Exception:
            self.layer_counter = 1
        self.cleanup_layers()
        self.refresh_layers_list()

    def waypoint_layer_key(self, waypoint: dict) -> tuple[str, int]:
        return str(waypoint["source"]), int(waypoint["source_id"])

    def cleanup_layers(self) -> None:
        changed = False
        valid_keys = {self.waypoint_layer_key(item) for item in self.display_waypoints}
        for layer_name in list(self.marker_layers.keys()):
            members = self.marker_layers[layer_name]
            filtered = {item for item in members if item in valid_keys}
            if filtered:
                if filtered != members:
                    changed = True
                self.marker_layers[layer_name] = filtered
                if layer_name not in self.layer_visibility:
                    self.layer_visibility[layer_name] = True
                    changed = True
            else:
                self.marker_layers.pop(layer_name, None)
                self.layer_visibility.pop(layer_name, None)
                changed = True
        if changed:
            self.save_layers_state()

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
        self.save_layers_state()
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
            self.set_status(self.t("status_select_waypoints_for_layer"))
            return
        layer_name = ""
        if dpg.does_item_exist("layer_name_input"):
            layer_name = str(dpg.get_value("layer_name_input")).strip()
        if not layer_name:
            layer_name = f"{self.t('tab_layers')} {self.layer_counter}"
            self.layer_counter += 1
            if dpg.does_item_exist("layer_name_input"):
                dpg.set_value("layer_name_input", layer_name)

        members = self.marker_layers.setdefault(layer_name, set())
        for waypoint_id in self.selected_waypoint_ids:
            if 0 <= waypoint_id < len(self.display_waypoints):
                members.add(self.waypoint_layer_key(self.display_waypoints[waypoint_id]))
        self.layer_visibility[layer_name] = True
        self.save_layers_state()
        self.refresh_layers_list()
        self.set_status(self.t("status_layer_added", name=layer_name, count=len(self.selected_waypoint_ids)))
