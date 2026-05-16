from __future__ import annotations

from contextlib import contextmanager
import json
from tkinter import Tk, filedialog
import ctypes
from ctypes import wintypes

import dearpygui.dearpygui as dpg

from app_constants import (
    DEFAULT_ALPHA_CUTOFF,
    DEFAULT_IMAGE_BLUR_RADIUS,
    DEFAULT_IMAGE_CONTRAST,
    DEFAULT_IMAGE_MASK_GROW_SHRINK,
    DEFAULT_IMAGE_NOISE_CLEANUP,
    DEFAULT_BRIGHTNESS_CUTOFF,
    DEFAULT_CONTOUR_EDGE_THRESHOLD,
    DEFAULT_CONTOUR_THICKNESS,
    DEFAULT_MAP_ZOOM_MULTIPLIER,
    DEFAULT_MAX_GENERATED_MARKERS,
    DEFAULT_MARKER_ZOOM_MULTIPLIER,
    MAX_MARKERS_ON_SCREEN,
    PROJECT_ROOT,
    RESOURCE_ROOT,
    SQUARE_RENDER_THRESHOLD,
    USER_DATA_DIR,
)


class UIBuildMixin:
    def load_settings_config(self) -> dict:
        defaults = {
            "max_markers_on_screen": MAX_MARKERS_ON_SCREEN,
            "square_render_threshold": SQUARE_RENDER_THRESHOLD,
            "map_zoom_multiplier": DEFAULT_MAP_ZOOM_MULTIPLIER,
            "marker_zoom_multiplier": DEFAULT_MARKER_ZOOM_MULTIPLIER,
        }
        path = USER_DATA_DIR / "settings.json"
        if not path.exists():
            return defaults
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return defaults
        if not isinstance(loaded, dict):
            return defaults
        result = dict(defaults)
        try:
            result["max_markers_on_screen"] = max(1, int(loaded.get("max_markers_on_screen", defaults["max_markers_on_screen"])))
        except Exception:
            pass
        try:
            result["square_render_threshold"] = max(1, int(loaded.get("square_render_threshold", defaults["square_render_threshold"])))
        except Exception:
            pass
        try:
            result["map_zoom_multiplier"] = max(0.2, min(4.0, float(loaded.get("map_zoom_multiplier", defaults["map_zoom_multiplier"]))))
        except Exception:
            pass
        try:
            result["marker_zoom_multiplier"] = max(0.2, min(6.0, float(loaded.get("marker_zoom_multiplier", defaults["marker_zoom_multiplier"]))))
        except Exception:
            pass
        return result

    def save_settings_config(self) -> None:
        path = USER_DATA_DIR / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "max_markers_on_screen": int(self.max_markers_on_screen),
            "square_render_threshold": int(self.square_render_threshold),
            "map_zoom_multiplier": float(self.map_zoom_multiplier),
            "marker_zoom_multiplier": float(self.marker_zoom_multiplier),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def sync_optimization_settings_ui(self) -> None:
        if dpg.does_item_exist("marker_screen_limit_input"):
            dpg.set_value("marker_screen_limit_input", int(self.max_markers_on_screen))
        if dpg.does_item_exist("marker_square_threshold_input"):
            dpg.set_value("marker_square_threshold_input", int(self.square_render_threshold))

    def sync_view_calibration_ui(self) -> None:
        if dpg.does_item_exist("map_zoom_multiplier_slider"):
            dpg.set_value("map_zoom_multiplier_slider", float(self.map_zoom_multiplier))
        if dpg.does_item_exist("map_zoom_multiplier_input"):
            dpg.set_value("map_zoom_multiplier_input", float(self.map_zoom_multiplier))
        if dpg.does_item_exist("marker_zoom_multiplier_slider"):
            dpg.set_value("marker_zoom_multiplier_slider", float(self.marker_zoom_multiplier))
        if dpg.does_item_exist("marker_zoom_multiplier_input"):
            dpg.set_value("marker_zoom_multiplier_input", float(self.marker_zoom_multiplier))

    def write_ui_config_file(self) -> None:
        path = USER_DATA_DIR / "ui_config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.ui_config, ensure_ascii=False, indent=2), encoding="utf-8")

    def apply_sidebar_width(self, width: float | int, persist: bool = False) -> None:
        self.ui_config["sidebar_width"] = max(260, min(700, int(round(width))))
        if dpg.does_item_exist("sidebar"):
            dpg.configure_item("sidebar", width=int(self.ui_config["sidebar_width"]))
        if dpg.does_item_exist("ui_sidebar_width_input"):
            current = int(dpg.get_value("ui_sidebar_width_input"))
            if current != int(self.ui_config["sidebar_width"]):
                dpg.set_value("ui_sidebar_width_input", int(self.ui_config["sidebar_width"]))
        if persist:
            self.write_ui_config_file()
        self.needs_redraw = True

    def get_image_parser_mode_options(self) -> list[str]:
        return [
            self.t("parser_mode_fill"),
            self.t("parser_mode_silhouette"),
            self.t("parser_mode_detail_edges"),
        ]

    def get_image_parser_mode_label(self, mode: str | None = None) -> str:
        mode_key = mode or getattr(self, "image_parser_mode", "fill")
        mode_map = {
            "fill": self.t("parser_mode_fill"),
            "silhouette": self.t("parser_mode_silhouette"),
            "detail_edges": self.t("parser_mode_detail_edges"),
        }
        return mode_map.get(mode_key, mode_map["fill"])

    def refresh_image_parser_mode_ui(self) -> None:
        if not dpg.does_item_exist("image_parser_mode_combo"):
            return
        dpg.configure_item("image_parser_mode_combo", items=self.get_image_parser_mode_options())
        dpg.set_value("image_parser_mode_combo", self.get_image_parser_mode_label())

    def apply_image_parser_mode_from_ui(self, sender=None, app_data=None, user_data=None) -> None:
        label = str(app_data if app_data is not None else dpg.get_value("image_parser_mode_combo"))
        reverse_map = {
            self.t("parser_mode_fill"): "fill",
            self.t("parser_mode_silhouette"): "silhouette",
            self.t("parser_mode_detail_edges"): "detail_edges",
        }
        self.image_parser_mode = reverse_map.get(label, "fill")
        self.on_image_settings_changed(sender, app_data, user_data)

    def reset_optimization_to_defaults(self, sender=None, app_data=None, user_data=None) -> None:
        self.max_markers_on_screen = MAX_MARKERS_ON_SCREEN
        self.square_render_threshold = SQUARE_RENDER_THRESHOLD
        self.settings_config["max_markers_on_screen"] = int(self.max_markers_on_screen)
        self.settings_config["square_render_threshold"] = int(self.square_render_threshold)
        self.save_settings_config()
        self.sync_optimization_settings_ui()
        self.overlay_cache_key = None
        self.needs_redraw = True
        self.set_status(
            self.t(
                "status_optimization_reset",
                screen=self.max_markers_on_screen,
                squares=self.square_render_threshold,
            )
        )

    def apply_view_calibration_settings(self, sender=None, app_data=None, user_data=None) -> None:
        old_map_zoom = max(0.01, float(self.map_zoom_multiplier))
        self.map_zoom_multiplier = max(
            0.2,
            min(4.0, float(dpg.get_value("map_zoom_multiplier_input"))),
        )
        self.marker_zoom_multiplier = max(
            0.2,
            min(6.0, float(dpg.get_value("marker_zoom_multiplier_input"))),
        )
        self.settings_config["map_zoom_multiplier"] = float(self.map_zoom_multiplier)
        self.settings_config["marker_zoom_multiplier"] = float(self.marker_zoom_multiplier)
        self.save_settings_config()
        self.sync_view_calibration_ui()
        self.scale = self.clamp_map_scale(self.scale * (self.map_zoom_multiplier / old_map_zoom))
        self.overlay_cache_key = None
        self.needs_redraw = True
        if dpg.does_item_exist("zoom_text"):
            dpg.set_value("zoom_text", self.t("zoom_label", scale=self.scale))
        self.set_status(
            self.t(
                "status_view_calibration_applied",
                map_zoom=self.map_zoom_multiplier,
                marker_zoom=self.marker_zoom_multiplier,
            )
        )

    def on_linked_int_control_changed(self, sender=None, app_data=None, user_data=None) -> None:
        if not isinstance(user_data, dict):
            return
        target_tag = str(user_data.get("target_tag", ""))
        callback = user_data.get("callback")
        value = int(app_data)
        if target_tag and dpg.does_item_exist(target_tag):
            current_value = int(dpg.get_value(target_tag))
            if current_value != value:
                dpg.set_value(target_tag, value)
        if callable(callback):
            callback(sender, value, None)

    def on_linked_float_control_changed(self, sender=None, app_data=None, user_data=None) -> None:
        if not isinstance(user_data, dict):
            return
        target_tag = str(user_data.get("target_tag", ""))
        callback = user_data.get("callback")
        value = float(app_data)
        if target_tag and dpg.does_item_exist(target_tag):
            current_value = float(dpg.get_value(target_tag))
            if abs(current_value - value) > 1e-6:
                dpg.set_value(target_tag, value)
        if callable(callback):
            callback(sender, value, None)

    def add_linked_int_control(
        self,
        *,
        slider_tag: str,
        input_tag: str,
        default_value: int,
        min_value: int,
        max_value: int,
        callback,
    ) -> None:
        with dpg.group(horizontal=True):
            dpg.add_slider_int(
                tag=slider_tag,
                default_value=default_value,
                min_value=min_value,
                max_value=max_value,
                width=-90,
                callback=self.on_linked_int_control_changed,
                user_data={"target_tag": input_tag, "callback": callback},
            )
            dpg.add_input_int(
                tag=input_tag,
                default_value=default_value,
                min_value=min_value,
                max_value=max_value,
                min_clamped=True,
                max_clamped=True,
                width=82,
                callback=self.on_linked_int_control_changed,
                user_data={"target_tag": slider_tag, "callback": callback},
            )

    def add_linked_float_control(
        self,
        *,
        slider_tag: str,
        input_tag: str,
        default_value: float,
        min_value: float,
        max_value: float,
        callback,
        format: str = "%.2f",
    ) -> None:
        with dpg.group(horizontal=True):
            dpg.add_slider_float(
                tag=slider_tag,
                default_value=default_value,
                min_value=min_value,
                max_value=max_value,
                width=-90,
                format=format,
                callback=self.on_linked_float_control_changed,
                user_data={"target_tag": input_tag, "callback": callback},
            )
            dpg.add_input_float(
                tag=input_tag,
                default_value=default_value,
                min_value=min_value,
                max_value=max_value,
                min_clamped=True,
                max_clamped=True,
                width=82,
                format=format,
                callback=self.on_linked_float_control_changed,
                user_data={"target_tag": slider_tag, "callback": callback},
            )

    @contextmanager
    def subsection_panel(self, indent: int = 14):
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=indent)
            with dpg.child_window(
                width=-1,
                auto_resize_y=True,
                border=False,
                no_scrollbar=True,
            ) as panel:
                if dpg.does_item_exist(self.ui_subsection_theme_tag):
                    dpg.bind_item_theme(panel, self.ui_subsection_theme_tag)
                yield panel

    @contextmanager
    def subsection_header(self, label: str, default_open: bool = False, indent: int = 18, tag: str | None = None):
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=indent)
            with dpg.group(width=-1):
                with dpg.collapsing_header(label=label, default_open=default_open, tag=tag) as header:
                    if dpg.does_item_exist(self.ui_subsection_header_theme_tag):
                        dpg.bind_item_theme(header, self.ui_subsection_header_theme_tag)
                    yield header

    def on_ui_setting_changed(self, sender=None, app_data=None, user_data=None) -> None:
        self.apply_ui_theme()
        self.needs_redraw = True

    def center_modal(self, tag: str, width: int, height: int) -> None:
        if not dpg.does_item_exist(tag):
            return
        viewport_w = max(1, int(dpg.get_viewport_client_width()))
        viewport_h = max(1, int(dpg.get_viewport_client_height()))
        viewport_x, viewport_y = dpg.get_viewport_pos()
        pos_x = viewport_x + max(0, (viewport_w - width) // 2)
        pos_y = viewport_y + max(0, (viewport_h - height) // 2)
        dpg.set_item_pos(tag, (pos_x, pos_y))

    def show_centered_modal(self, tag: str, width: int, height: int) -> None:
        if not dpg.does_item_exist(tag):
            return
        dpg.configure_item(tag, show=True)
        self.center_modal(tag, width, height)

    def get_language_options(self) -> list[str]:
        return [self.t("language_ru"), self.t("language_en")]

    def refresh_language_settings_ui(self) -> None:
        options = self.get_language_options()
        current = self.t("language_ru") if self.language == "ru" else self.t("language_en")
        if dpg.does_item_exist("language_combo"):
            dpg.configure_item("language_combo", items=options)
            dpg.set_value("language_combo", current)
        if dpg.does_item_exist("onboarding_language_combo"):
            dpg.configure_item("onboarding_language_combo", items=options)
            dpg.set_value("onboarding_language_combo", current)

    def apply_language_from_ui(self, sender=None, app_data=None, user_data=None) -> None:
        source_tag = str(user_data or "language_combo")
        if not dpg.does_item_exist(source_tag):
            return
        selected = str(dpg.get_value(source_tag))
        language = "ru" if selected == self.t("language_ru") else "en"
        self.language = self.core.set_language(language)
        self.language_setup_required = False
        self.refresh_language_settings_ui()
        self.refresh_exbo_settings_ui()
        self.refresh_localized_ui()
        lang_name = self.t("language_ru") if self.language == "ru" else self.t("language_en")
        self.set_status(
            f"{self.t('status_language_saved', lang_name=lang_name)} {self.t('language_restart_note')}"
        )

    def refresh_localized_ui(self) -> None:
        label_updates = {
            "main_window": self.t("app_title"),
            "onboarding_modal": self.t("first_launch_setup"),
            "tab_main": self.t("tab_main"),
            "tab_image": self.t("tab_image"),
            "tab_layers": self.t("tab_layers"),
            "tab_settings": self.t("tab_settings"),
            "tab_help": self.t("tab_help"),
            "header_map": self.t("section_map"),
            "header_regions": self.t("section_regions"),
            "header_marker_actions": self.t("section_marker_actions"),
            "header_create_waypoint": self.t("section_create_waypoint"),
            "header_waypoint_editor": self.t("section_waypoint_editor"),
            "header_source": self.t("section_source"),
            "header_parsing": self.t("section_parsing"),
            "header_contour": self.t("section_contour"),
            "header_parser_advanced": self.t("section_parser_advanced"),
            "header_layer_editor": self.t("section_layer_editor"),
            "header_exbo_cfg": self.t("section_exbo_cfg"),
            "header_language": self.t("section_language"),
            "header_optimization": self.t("section_optimization"),
            "header_view_calibration": self.t("section_view_calibration"),
            "header_ui": self.t("section_ui"),
            "header_layout": self.t("section_layout"),
            "header_marker_preview": self.t("section_marker_preview"),
            "header_colors": self.t("section_colors"),
            "header_controls": self.t("section_controls"),
            "header_notes": self.t("section_notes"),
            "fit_to_map_button": self.t("fit_to_map"),
            "enable_all_regions_button": self.t("enable_all_regions"),
            "disable_all_regions_button": self.t("disable_all_regions"),
            "save_changes_button": self.t("save_changes"),
            "center_selected_button": self.t("center_selected"),
            "delete_selected_button": self.t("delete_selected"),
            "create_waypoint_button": self.t("create_waypoint"),
            "selected_waypoint_apply_button": self.t("apply_style_selected"),
            "open_image_button": self.t("open_image"),
            "reload_image_button": self.t("reload_image"),
            "parse_image_button": self.t("parse_image"),
            "browse_exbo_button": self.t("browse_exbo"),
            "apply_exbo_path_button": self.t("apply_exbo_path"),
            "language_apply_button": self.t("language_apply"),
            "apply_optimization_button": self.t("apply_optimization"),
            "reset_optimization_button": self.t("reset_optimization_defaults"),
            "apply_view_calibration_button": self.t("apply_view_calibration"),
            "save_ui_config_button": self.t("save_ui_config"),
            "add_selected_to_layer_button": self.t("add_selected_to_layer"),
            "onboarding_browse_button": self.t("browse"),
            "onboarding_apply_button": self.t("onboarding_apply"),
        }
        for tag, label in label_updates.items():
            if dpg.does_item_exist(tag):
                dpg.set_item_label(tag, label)

        value_updates = {
            "app_title_text": self.t("app_title"),
            "map_section_title_text": self.t("section_map"),
            "regions_hint_text": self.t("regions_hint"),
            "source_title_text": self.t("image_to_markers"),
            "image_preview_hint_text": self.t("image_preview_hint"),
            "new_waypoint_hint_text": self.t("new_waypoint_hint"),
            "image_max_markers_label": self.t("max_markers"),
            "image_parser_mode_label": self.t("parser_mode"),
            "image_alpha_cutoff_label": self.t("alpha_cutoff"),
            "image_sampling_step_label": self.t("sampling_grid_step"),
            "image_parsing_icon_label": self.t("field_icon"),
            "image_brightness_cutoff_label": self.t("brightness_cutoff"),
            "image_contour_thickness_label": self.t("contour_thickness"),
            "image_contrast_label": self.t("image_contrast"),
            "image_blur_radius_label": self.t("image_blur_radius"),
            "image_mask_grow_shrink_label": self.t("image_mask_grow_shrink"),
            "image_noise_cleanup_label": self.t("image_noise_cleanup"),
            "image_contour_edge_threshold_label": self.t("image_contour_edge_threshold"),
            "image_contour_help_text": self.t("contour_only_hint"),
            "image_parser_advanced_hint_text": self.t("image_parser_advanced_hint"),
            "layer_editor_title_text": self.t("layer_editor_title"),
            "layer_hint_text": self.t("layer_hint"),
            "exbo_folder_label": self.t("exbo_folder"),
            "language_label_text": self.t("language_label"),
            "onboarding_title_text": self.t("first_launch_setup"),
            "onboarding_hint_text": self.t("onboarding_hint"),
            "onboarding_language_label_text": self.t("language_label"),
            "onboarding_exbo_label_text": self.t("exbo_folder"),
            "language_restart_note_text": self.t("language_restart_note"),
            "optimization_markers_label": self.t("markers_on_screen"),
            "optimization_squares_label": self.t("squares_after"),
            "map_zoom_multiplier_label": self.t("map_zoom_multiplier"),
            "marker_zoom_multiplier_label": self.t("marker_zoom_multiplier"),
            "ui_sidebar_width_label": self.t("sidebar_width"),
            "ui_rounding_label": self.t("rounding"),
            "ui_preview_alpha_label": self.t("preview_alpha"),
            "ui_preview_radius_small_label": self.t("preview_radius_small"),
            "ui_preview_radius_big_label": self.t("preview_radius_big"),
            "ui_background_color_label": self.t("background_color"),
            "ui_panel_color_label": self.t("panel_color"),
            "ui_frame_color_label": self.t("frame_color"),
            "ui_accent_color_label": self.t("accent_color"),
            "help_title_text": self.t("help_title"),
            "help_control_pan_text": self.t("control_pan"),
            "help_control_zoom_text": self.t("control_zoom"),
            "help_control_select_text": self.t("control_select"),
            "help_control_delete_text": self.t("control_delete"),
            "help_control_delete_image_text": self.t("control_delete_image"),
            "help_control_hide_text": self.t("control_hide"),
            "help_control_undo_text": self.t("control_undo"),
            "help_note_parse_text": self.t("help_note_parse"),
            "help_note_layers_text": self.t("help_note_layers"),
            "help_note_ui_text": self.t("help_note_ui"),
        }
        for tag, value in value_updates.items():
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, value)

        if dpg.does_item_exist("status_text"):
            current_status = str(dpg.get_value("status_text")).strip()
            if not current_status or current_status == self.t("status_ready"):
                dpg.set_value("status_text", self.t("status_ready"))
        if dpg.does_item_exist("progress_text") and not self.active_map:
            dpg.set_value("progress_text", self.t("progress_zero"))
        elif dpg.does_item_exist("progress_text") and self.active_map is not None:
            dpg.set_value(
                "progress_text",
                self.t(
                    "progress_zone_memory",
                    loaded=len(self.tile_textures),
                    visible=len(self.visible_tile_targets),
                    enabled=len(self.enabled_zone_names),
                    total=len(self.active_map.zones),
                ),
            )
        if dpg.does_item_exist("zoom_text"):
            dpg.set_value("zoom_text", self.t("zoom_label", scale=self.scale))
        if dpg.does_item_exist("image_marker_estimate_text"):
            self.update_image_marker_estimate(None if self.image_preview_marker_cache_key is None else len(self.image_preview_marker_cache_points))
        if dpg.does_item_exist("generated_status"):
            current_generated = str(dpg.get_value("generated_status")).strip()
            if not current_generated or current_generated == self.t("generated_buffer_empty"):
                dpg.set_value("generated_status", self.t("generated_buffer_empty"))
        self.refresh_selected_waypoint_editor()
        self.refresh_waypoint_list()
        self.refresh_zone_list()
        self.refresh_layers_list()
        self.refresh_exbo_settings_ui()
        self.refresh_language_settings_ui()
        self.refresh_image_parser_mode_ui()
        self.sync_optimization_settings_ui()
        self.sync_view_calibration_ui()
        if hasattr(dpg, "set_viewport_title"):
            dpg.set_viewport_title(self.t("app_title"))
        if dpg.does_item_exist("onboarding_modal") and dpg.is_item_shown("onboarding_modal"):
            self.center_modal("onboarding_modal", 620, 300)

    def create_onboarding_modal(self) -> None:
        if dpg.does_item_exist("onboarding_modal"):
            return
        with dpg.window(
            tag="onboarding_modal",
            label=self.t("first_launch_setup"),
            modal=True,
            no_close=True,
            no_resize=True,
            no_collapse=True,
            show=False,
            width=620,
            height=300,
        ):
            dpg.add_text(self.t("first_launch_setup"), color=(255, 221, 120), tag="onboarding_title_text")
            dpg.add_text(self.t("onboarding_hint"), tag="onboarding_hint_text", wrap=560)
            dpg.add_spacer(height=6)
            dpg.add_text(self.t("language_label"), tag="onboarding_language_label_text")
            dpg.add_combo(items=self.get_language_options(), tag="onboarding_language_combo", width=-1)
            dpg.add_spacer(height=8)
            dpg.add_text(self.t("exbo_folder"), tag="onboarding_exbo_label_text")
            dpg.add_input_text(tag="onboarding_exbo_input", width=-1)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label=self.t("browse"),
                    tag="onboarding_browse_button",
                    width=160,
                    callback=self.browse_exbo_dir,
                )
                dpg.add_button(
                    label=self.t("onboarding_apply"),
                    tag="onboarding_apply_button",
                    width=-1,
                    callback=self.apply_onboarding_from_ui,
                )

    def sync_exbo_inputs(self, value: str) -> None:
        if dpg.does_item_exist("exbo_dir_input"):
            dpg.set_value("exbo_dir_input", value)
        if dpg.does_item_exist("onboarding_exbo_input"):
            dpg.set_value("onboarding_exbo_input", value)

    def refresh_exbo_settings_ui(self) -> None:
        exbo_dir = str(self.core.get_exbo_dir())
        self.sync_exbo_inputs(exbo_dir)
        cfg_path = str(self.core.get_waypoints_path())
        if dpg.does_item_exist("exbo_cfg_path_text"):
            dpg.set_value("exbo_cfg_path_text", self.t("cfg_path", path=cfg_path))
        if dpg.does_item_exist("exbo_status_text"):
            configured = not self.core.requires_exbo_setup()
            dpg.set_value(
                "exbo_status_text",
                self.t("exbo_path_configured") if configured else self.t("exbo_path_not_configured"),
            )

    def browse_exbo_dir(self, sender=None, app_data=None, user_data=None) -> None:
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        initial_dir = str(self.core.get_exbo_dir())
        selected = filedialog.askdirectory(
            title=self.t("browse_exbo_title"),
            initialdir=initial_dir if initial_dir else None,
            mustexist=True,
        )
        root.destroy()
        if selected:
            self.sync_exbo_inputs(selected)

    def apply_onboarding_from_ui(self, sender=None, app_data=None, user_data=None) -> None:
        selected = ""
        if dpg.does_item_exist("onboarding_language_combo"):
            selected = str(dpg.get_value("onboarding_language_combo"))
        language = "ru" if selected == self.t("language_ru") else "en"
        self.language = self.core.set_language(language)
        self.language_setup_required = False
        self.refresh_language_settings_ui()
        self.refresh_localized_ui()

        path_value = ""
        if dpg.does_item_exist("onboarding_exbo_input"):
            path_value = str(dpg.get_value("onboarding_exbo_input")).strip()
        if not path_value:
            self.exbo_setup_required = True
            self.set_status(self.t("status_enter_exbo_path"))
            self.show_centered_modal("onboarding_modal", 620, 300)
            return
        try:
            chosen_dir = self.core.set_exbo_dir(path_value)
        except Exception as error:
            self.exbo_setup_required = True
            self.set_status(self.t("status_exbo_path_error", error=error))
            self.show_centered_modal("onboarding_modal", 620, 300)
            return

        self.sync_exbo_inputs(str(chosen_dir))
        self.exbo_setup_required = False
        self.refresh_exbo_settings_ui()
        self.load_waypoints()
        if dpg.does_item_exist("onboarding_modal"):
            dpg.configure_item("onboarding_modal", show=False)
        self.set_status(self.t("status_exbo_folder_set", path=chosen_dir))

    def apply_exbo_dir_from_ui(self, sender=None, app_data=None, user_data=None) -> None:
        source_tag = str(user_data or "exbo_dir_input")
        path_value = ""
        if dpg.does_item_exist(source_tag):
            path_value = str(dpg.get_value(source_tag)).strip()
        if not path_value:
            self.set_status(self.t("status_enter_exbo_path"))
            return
        try:
            chosen_dir = self.core.set_exbo_dir(path_value)
        except Exception as error:
            self.set_status(self.t("status_exbo_path_error", error=error))
            return

        self.sync_exbo_inputs(str(chosen_dir))
        self.refresh_exbo_settings_ui()
        self.exbo_setup_required = False
        self.load_waypoints()
        if dpg.does_item_exist("onboarding_modal"):
            dpg.configure_item("onboarding_modal", show=False)
        self.set_status(self.t("status_exbo_folder_set", path=chosen_dir))

    def load_ui_config(self) -> dict:
        defaults = {
            "sidebar_width": 360,
            "preview_point_alpha": 225,
            "preview_point_radius_small": 1.0,
            "preview_point_radius_big": 1.7,
            "ui_rounding": 6.0,
            "ui_bg_color": [31, 33, 41, 255],
            "ui_panel_color": [36, 38, 46, 255],
            "ui_frame_color": [52, 56, 69, 255],
            "ui_accent_color": [106, 178, 255, 255],
        }
        path = USER_DATA_DIR / "ui_config.json"
        if not path.exists():
            return defaults
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return defaults
        if not isinstance(loaded, dict):
            return defaults
        result = dict(defaults)
        for key in defaults:
            if key in loaded:
                result[key] = loaded[key]
        return self.normalize_ui_config(result)

    def normalize_ui_config(self, values: dict) -> dict:
        result = dict(values)
        result["sidebar_width"] = max(260, min(700, int(result["sidebar_width"])))
        result["preview_point_alpha"] = max(20, min(255, int(result["preview_point_alpha"])))
        result["preview_point_radius_small"] = max(0.6, min(4.0, float(result["preview_point_radius_small"])))
        result["preview_point_radius_big"] = max(0.8, min(8.0, float(result["preview_point_radius_big"])))
        result["ui_rounding"] = max(0.0, min(18.0, float(result["ui_rounding"])))
        for key in ("ui_bg_color", "ui_panel_color", "ui_frame_color", "ui_accent_color"):
            color = list(result[key])
            if len(color) < 4:
                color = (color + [255, 255, 255, 255])[:4]
            result[key] = [max(0, min(255, int(v))) for v in color[:4]]
        return result

    def get_ui_config_from_widgets(self) -> dict:
        if not dpg.does_item_exist("ui_sidebar_width_input"):
            return dict(self.ui_config)
        return self.normalize_ui_config(
            {
                "sidebar_width": dpg.get_value("ui_sidebar_width_input"),
                "preview_point_alpha": dpg.get_value("ui_preview_alpha_input"),
                "preview_point_radius_small": dpg.get_value("ui_preview_radius_small_input"),
                "preview_point_radius_big": dpg.get_value("ui_preview_radius_big_input"),
                "ui_rounding": dpg.get_value("ui_rounding_input"),
                "ui_bg_color": list(dpg.get_value("ui_bg_color_input")),
                "ui_panel_color": list(dpg.get_value("ui_panel_color_input")),
                "ui_frame_color": list(dpg.get_value("ui_frame_color_input")),
                "ui_accent_color": list(dpg.get_value("ui_accent_color_input")),
            }
        )

    def save_ui_config(self) -> None:
        self.ui_config = self.get_ui_config_from_widgets()
        self.write_ui_config_file()
        self.set_status(self.t("status_ui_config_saved", name="ui_config.json"))

    def apply_ui_theme(self) -> None:
        self.ui_config = self.get_ui_config_from_widgets()
        if dpg.does_item_exist(self.ui_theme_tag):
            dpg.delete_item(self.ui_theme_tag)
        if dpg.does_item_exist(self.ui_subsection_theme_tag):
            dpg.delete_item(self.ui_subsection_theme_tag)
        if dpg.does_item_exist(self.ui_subsection_header_theme_tag):
            dpg.delete_item(self.ui_subsection_header_theme_tag)

        sidebar_width = self.ui_config["sidebar_width"]
        bg = tuple(self.ui_config["ui_bg_color"])
        panel = tuple(self.ui_config["ui_panel_color"])
        frame = tuple(self.ui_config["ui_frame_color"])
        accent = tuple(self.ui_config["ui_accent_color"])
        rounding = float(self.ui_config["ui_rounding"])
        accent_soft = (
            min(255, accent[0] + 18),
            min(255, accent[1] + 18),
            min(255, accent[2] + 18),
            accent[3],
        )
        text_dim = (190, 198, 214, 255)
        border = (
            max(0, frame[0] - 8),
            max(0, frame[1] - 8),
            max(0, frame[2] - 8),
            255,
        )
        subsection_bg = (
            max(0, panel[0] - 10),
            max(0, panel[1] - 10),
            max(0, panel[2] - 10),
            max(90, panel[3]),
        )

        with dpg.theme(tag=self.ui_theme_tag):
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, bg)
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, panel)
                dpg.add_theme_color(dpg.mvThemeCol_PopupBg, panel)
                dpg.add_theme_color(dpg.mvThemeCol_Border, border)
                dpg.add_theme_color(dpg.mvThemeCol_Separator, border)
                dpg.add_theme_color(dpg.mvThemeCol_SeparatorHovered, accent)
                dpg.add_theme_color(dpg.mvThemeCol_SeparatorActive, accent)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, frame)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, accent_soft)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, accent)
                dpg.add_theme_color(dpg.mvThemeCol_Button, frame)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, accent_soft)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, accent)
                dpg.add_theme_color(dpg.mvThemeCol_Header, frame)
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, accent_soft)
                dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, accent)
                dpg.add_theme_color(dpg.mvThemeCol_Tab, frame)
                dpg.add_theme_color(dpg.mvThemeCol_TabHovered, accent_soft)
                dpg.add_theme_color(dpg.mvThemeCol_TabActive, accent)
                dpg.add_theme_color(dpg.mvThemeCol_TabUnfocused, frame)
                dpg.add_theme_color(dpg.mvThemeCol_TabUnfocusedActive, accent_soft)
                dpg.add_theme_color(dpg.mvThemeCol_TitleBg, panel)
                dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, frame)
                dpg.add_theme_color(dpg.mvThemeCol_CheckMark, accent)
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, accent_soft)
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, accent)
                dpg.add_theme_color(dpg.mvThemeCol_Text, (235, 238, 244, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, text_dim)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, rounding)
                dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, rounding)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, rounding)
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, rounding)
                dpg.add_theme_style(dpg.mvStyleVar_PopupRounding, rounding)
                dpg.add_theme_style(dpg.mvStyleVar_ScrollbarRounding, rounding)
                dpg.add_theme_style(dpg.mvStyleVar_TabRounding, rounding)
        with dpg.theme(tag=self.ui_subsection_theme_tag):
            with dpg.theme_component(dpg.mvChildWindow):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, subsection_bg)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, max(0.0, rounding - 1.0))
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 10, 8)
        with dpg.theme(tag=self.ui_subsection_header_theme_tag):
            with dpg.theme_component(dpg.mvCollapsingHeader):
                dpg.add_theme_color(dpg.mvThemeCol_Header, subsection_bg)
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, frame)
                dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, accent_soft)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, max(0.0, rounding - 1.0))
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 6)
        dpg.bind_theme(self.ui_theme_tag)
        if dpg.does_item_exist("sidebar"):
            dpg.configure_item("sidebar", width=sidebar_width)
        self.set_status(self.t("status_ui_theme_applied"))

    def build_main_tab(self) -> None:
        with dpg.tab(label=self.t("tab_main"), tag="tab_main"):
            with dpg.collapsing_header(label=self.t("section_map"), default_open=True, tag="header_map"):
                dpg.add_text(self.t("section_map"), color=(255, 221, 120), tag="map_section_title_text")
                dpg.add_text("", tag="map_name_text")
                dpg.add_button(label=self.t("fit_to_map"), tag="fit_to_map_button", width=-1, callback=self.on_fit_clicked)

            with dpg.collapsing_header(label=self.t("section_regions"), default_open=True, tag="header_regions"):
                dpg.add_button(label=self.t("enable_all_regions"), tag="enable_all_regions_button", width=-1, callback=lambda *_: self.enable_all_zones())
                dpg.add_button(label=self.t("disable_all_regions"), tag="disable_all_regions_button", width=-1, callback=lambda *_: self.disable_all_zones())
                dpg.add_text(self.t("regions_hint"), tag="regions_hint_text", wrap=320)
                with dpg.child_window(tag="zone_filter_list", height=220, border=True):
                    pass

            with dpg.collapsing_header(label=self.t("section_marker_actions"), default_open=False, tag="header_marker_actions"):
                dpg.add_text(self.t("markers_count", count=0), tag="waypoint_count_text")
                dpg.add_button(label=self.t("save_changes"), tag="save_changes_button", width=-1, callback=self.on_save_changes_clicked)
                dpg.add_button(label=self.t("center_selected"), tag="center_selected_button", width=-1, callback=self.on_center_selected_clicked)
                dpg.add_button(label=self.t("delete_selected"), tag="delete_selected_button", width=-1, callback=self.on_delete_selected_clicked)

            with dpg.collapsing_header(label=self.t("section_create_waypoint"), default_open=False, tag="header_create_waypoint"):
                dpg.add_text(self.t("field_name"))
                dpg.add_input_text(tag="new_waypoint_name_input", width=-1, default_value="")
                dpg.add_text(self.t("new_waypoint_hint"), tag="new_waypoint_hint_text", wrap=320)
                dpg.add_text(self.t("field_color"))
                dpg.add_color_edit(
                    tag="new_waypoint_color_input",
                    default_value=[255, 255, 255, 255],
                    alpha_bar=True,
                    width=-1,
                )
                dpg.add_text(self.t("field_icon_shape"))
                dpg.add_combo(
                    items=self.get_waypoint_icon_labels(),
                    tag="new_waypoint_icon_combo",
                    width=-1,
                    default_value=self.get_waypoint_icon_labels()[0],
                )
                dpg.add_button(
                    label=self.t("create_waypoint"),
                    tag="create_waypoint_button",
                    width=-1,
                    callback=self.on_create_waypoint_clicked,
                )

            with dpg.collapsing_header(label=self.t("section_waypoint_editor"), default_open=False, tag="header_waypoint_editor"):
                dpg.add_text(self.t("selected_count", count=0), tag="selected_waypoints_info_text")
                dpg.add_text(self.t("field_name"))
                dpg.add_input_text(tag="selected_waypoint_name_input", width=-1, default_value="")
                dpg.add_text("", tag="selected_waypoint_name_note", wrap=320)
                dpg.add_text(self.t("field_color"))
                dpg.add_color_edit(
                    tag="selected_waypoint_color_input",
                    default_value=[255, 255, 255, 255],
                    alpha_bar=True,
                    width=-1,
                )
                dpg.add_text(self.t("field_icon_shape"))
                dpg.add_combo(
                    items=self.get_waypoint_icon_labels(),
                    tag="selected_waypoint_icon_combo",
                    width=-1,
                    default_value=self.get_waypoint_icon_labels()[0],
                )
                dpg.add_button(
                    label=self.t("apply_style_selected"),
                    tag="selected_waypoint_apply_button",
                    width=-1,
                    callback=self.on_apply_selected_waypoint_style_clicked,
                )

    def build_image_tab(self) -> None:
        with dpg.tab(label=self.t("tab_image"), tag="tab_image"):
            with dpg.collapsing_header(label=self.t("section_source"), default_open=True, tag="header_source"):
                dpg.add_text(self.t("image_to_markers"), color=(255, 221, 120), tag="source_title_text")
                dpg.add_input_text(tag="image_path_input", width=-1, readonly=True, default_value="")
                dpg.add_button(label=self.t("open_image"), tag="open_image_button", width=-1, callback=self.on_open_image_clicked)
                dpg.add_button(label=self.t("reload_image"), tag="reload_image_button", width=-1, callback=self.on_reload_image_clicked)
                dpg.add_text(self.t("image_preview_hint"), tag="image_preview_hint_text", wrap=320)

            with dpg.collapsing_header(label=self.t("section_parsing"), default_open=True, tag="header_parsing"):
                dpg.add_text(self.t("parser_mode"), tag="image_parser_mode_label")
                dpg.add_combo(
                    items=self.get_image_parser_mode_options(),
                    tag="image_parser_mode_combo",
                    width=-1,
                    default_value=self.get_image_parser_mode_label(),
                    callback=self.apply_image_parser_mode_from_ui,
                )
                dpg.add_checkbox(
                    label=self.t("include_background"),
                    tag="image_include_background_input",
                    default_value=False,
                    callback=self.on_image_settings_changed,
                )
                dpg.add_text(self.t("alpha_cutoff"), tag="image_alpha_cutoff_label")
                self.add_linked_int_control(
                    slider_tag="image_alpha_cutoff_slider",
                    input_tag="image_alpha_cutoff_input",
                    default_value=DEFAULT_ALPHA_CUTOFF,
                    min_value=0,
                    max_value=255,
                    callback=self.on_image_settings_changed,
                )
                dpg.add_text(self.t("sampling_grid_step"), tag="image_sampling_step_label")
                self.add_linked_int_control(
                    slider_tag="image_sampling_step_slider",
                    input_tag="image_sampling_step_input",
                    default_value=1,
                    min_value=1,
                    max_value=32,
                    callback=self.on_image_settings_changed,
                )
                dpg.add_text(self.t("max_markers"), tag="image_max_markers_label")
                dpg.add_input_int(
                    tag="image_marker_limit_input",
                    default_value=DEFAULT_MAX_GENERATED_MARKERS,
                    min_value=1,
                    min_clamped=True,
                    width=-1,
                    callback=self.on_image_settings_changed,
                )
                dpg.add_text(self.t("estimated_markers_empty"), tag="image_marker_estimate_text")

                with dpg.collapsing_header(label=self.t("section_contour"), default_open=False, tag="header_contour"):
                    dpg.add_text(self.t("brightness_cutoff"), tag="image_brightness_cutoff_label")
                    self.add_linked_int_control(
                        slider_tag="image_brightness_cutoff_slider",
                        input_tag="image_brightness_cutoff_input",
                        default_value=DEFAULT_BRIGHTNESS_CUTOFF,
                        min_value=0,
                        max_value=255,
                        callback=self.on_image_settings_changed,
                    )
                    dpg.add_text(self.t("contour_thickness"), tag="image_contour_thickness_label")
                    self.add_linked_int_control(
                        slider_tag="image_contour_thickness_slider",
                        input_tag="image_contour_thickness_input",
                        default_value=DEFAULT_CONTOUR_THICKNESS,
                        min_value=1,
                        max_value=8,
                        callback=self.on_image_settings_changed,
                    )
                    dpg.add_text(self.t("image_contour_edge_threshold"), tag="image_contour_edge_threshold_label")
                    self.add_linked_int_control(
                        slider_tag="image_contour_edge_threshold_slider",
                        input_tag="image_contour_edge_threshold_input",
                        default_value=DEFAULT_CONTOUR_EDGE_THRESHOLD,
                        min_value=0,
                        max_value=255,
                        callback=self.on_image_settings_changed,
                    )
                    dpg.add_text(self.t("contour_only_hint"), tag="image_contour_help_text", wrap=320)

                with dpg.collapsing_header(label=self.t("section_parser_advanced"), default_open=False, tag="header_parser_advanced"):
                    dpg.add_text(self.t("image_contrast"), tag="image_contrast_label")
                    self.add_linked_float_control(
                        slider_tag="image_contrast_slider",
                        input_tag="image_contrast_input",
                        default_value=DEFAULT_IMAGE_CONTRAST,
                        min_value=0.2,
                        max_value=3.0,
                        callback=self.on_image_settings_changed,
                        format="%.2f",
                    )
                    dpg.add_text(self.t("image_blur_radius"), tag="image_blur_radius_label")
                    self.add_linked_float_control(
                        slider_tag="image_blur_radius_slider",
                        input_tag="image_blur_radius_input",
                        default_value=DEFAULT_IMAGE_BLUR_RADIUS,
                        min_value=0.0,
                        max_value=4.0,
                        callback=self.on_image_settings_changed,
                        format="%.2f",
                    )
                    dpg.add_text(self.t("image_mask_grow_shrink"), tag="image_mask_grow_shrink_label")
                    self.add_linked_int_control(
                        slider_tag="image_mask_grow_shrink_slider",
                        input_tag="image_mask_grow_shrink_input",
                        default_value=DEFAULT_IMAGE_MASK_GROW_SHRINK,
                        min_value=-6,
                        max_value=6,
                        callback=self.on_image_settings_changed,
                    )
                    dpg.add_text(self.t("image_noise_cleanup"), tag="image_noise_cleanup_label")
                    self.add_linked_int_control(
                        slider_tag="image_noise_cleanup_slider",
                        input_tag="image_noise_cleanup_input",
                        default_value=DEFAULT_IMAGE_NOISE_CLEANUP,
                        min_value=0,
                        max_value=8,
                        callback=self.on_image_settings_changed,
                    )
                    dpg.add_text(self.t("image_parser_advanced_hint"), tag="image_parser_advanced_hint_text", wrap=320)

                dpg.add_text(self.t("field_icon"), tag="image_parsing_icon_label")
                dpg.add_combo(
                    items=self.get_waypoint_icon_labels(),
                    tag="image_icon_input",
                    width=-1,
                    default_value=self.get_waypoint_icon_labels()[0],
                )
                dpg.add_checkbox(label=self.t("auto_icons"), tag="image_auto_icons_input", default_value=True)
                dpg.add_button(label=self.t("parse_image"), tag="parse_image_button", width=-1, callback=self.on_generate_image_clicked)
                dpg.add_text(self.t("generated_buffer_empty"), tag="generated_status", wrap=320)

    def build_layers_tab(self) -> None:
        with dpg.tab(label=self.t("tab_layers"), tag="tab_layers"):
            with dpg.collapsing_header(label=self.t("section_layer_editor"), default_open=True, tag="header_layer_editor"):
                dpg.add_text(self.t("layer_editor_title"), color=(255, 221, 120), tag="layer_editor_title_text")
                dpg.add_input_text(tag="layer_name_input", hint=self.t("layer_name_hint"), width=-1)
                dpg.add_button(label=self.t("add_selected_to_layer"), tag="add_selected_to_layer_button", width=-1, callback=lambda *_: self.add_selection_to_layer())
                dpg.add_text(self.t("layer_hint"), tag="layer_hint_text", wrap=320)
                with dpg.child_window(tag="layers_list", height=260, border=True):
                    pass

    def build_settings_tab(self) -> None:
        with dpg.tab(label=self.t("tab_settings"), tag="tab_settings"):
            with dpg.collapsing_header(label=self.t("section_exbo_cfg"), default_open=False, tag="header_exbo_cfg"):
                with self.subsection_panel():
                    dpg.add_text(self.t("exbo_folder"), tag="exbo_folder_label")
                    dpg.add_input_text(tag="exbo_dir_input", width=-1)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label=self.t("browse_exbo"), tag="browse_exbo_button", width=150, callback=self.browse_exbo_dir)
                        dpg.add_button(
                            label=self.t("apply_exbo_path"),
                            tag="apply_exbo_path_button",
                            width=-1,
                            callback=self.apply_exbo_dir_from_ui,
                            user_data="exbo_dir_input",
                        )
                    dpg.add_text("", tag="exbo_status_text", wrap=320)
                    dpg.add_text("", tag="exbo_cfg_path_text", wrap=320)

            with dpg.collapsing_header(label=self.t("section_language"), default_open=False, tag="header_language"):
                with self.subsection_panel():
                    dpg.add_text(self.t("language_label"), tag="language_label_text")
                    dpg.add_combo(items=self.get_language_options(), tag="language_combo", width=-1)
                    dpg.add_button(label=self.t("language_apply"), tag="language_apply_button", width=-1, callback=self.apply_language_from_ui)
                    dpg.add_text(self.t("language_restart_note"), tag="language_restart_note_text", wrap=320)

            with dpg.collapsing_header(label=self.t("section_optimization"), default_open=True, tag="header_optimization"):
                with self.subsection_panel():
                    dpg.add_text(self.t("markers_on_screen"), tag="optimization_markers_label")
                    dpg.add_input_int(
                        tag="marker_screen_limit_input",
                        default_value=self.max_markers_on_screen or MAX_MARKERS_ON_SCREEN,
                        min_value=1,
                        min_clamped=True,
                        width=-1,
                    )
                    dpg.add_text(self.t("squares_after"), tag="optimization_squares_label")
                    dpg.add_input_int(
                        tag="marker_square_threshold_input",
                        default_value=self.square_render_threshold or SQUARE_RENDER_THRESHOLD,
                        min_value=1,
                        min_clamped=True,
                        width=-1,
                    )
                    dpg.add_button(label=self.t("apply_optimization"), tag="apply_optimization_button", width=-1, callback=self.on_apply_optimization_clicked)
                    dpg.add_button(label=self.t("reset_optimization_defaults"), tag="reset_optimization_button", width=-1, callback=self.reset_optimization_to_defaults)

            with dpg.collapsing_header(label=self.t("section_view_calibration"), default_open=False, tag="header_view_calibration"):
                with self.subsection_panel():
                    dpg.add_text(self.t("map_zoom_multiplier"), tag="map_zoom_multiplier_label")
                    self.add_linked_float_control(
                        slider_tag="map_zoom_multiplier_slider",
                        input_tag="map_zoom_multiplier_input",
                        default_value=float(self.map_zoom_multiplier),
                        min_value=0.4,
                        max_value=2.5,
                        callback=lambda *_: None,
                        format="%.2f",
                    )
                    dpg.add_text(self.t("marker_zoom_multiplier"), tag="marker_zoom_multiplier_label")
                    self.add_linked_float_control(
                        slider_tag="marker_zoom_multiplier_slider",
                        input_tag="marker_zoom_multiplier_input",
                        default_value=float(self.marker_zoom_multiplier),
                        min_value=0.4,
                        max_value=4.0,
                        callback=lambda *_: None,
                        format="%.2f",
                    )
                    dpg.add_button(
                        label=self.t("apply_view_calibration"),
                        tag="apply_view_calibration_button",
                        width=-1,
                        callback=self.apply_view_calibration_settings,
                    )

            with dpg.collapsing_header(label=self.t("section_ui"), default_open=False, tag="header_ui"):
                with self.subsection_header(label=self.t("section_layout"), default_open=True, indent=18, tag="header_layout"):
                    with self.subsection_panel():
                        dpg.add_text(self.t("sidebar_width"), tag="ui_sidebar_width_label")
                        dpg.add_input_int(
                            tag="ui_sidebar_width_input",
                            default_value=int(self.ui_config["sidebar_width"]),
                            min_value=260,
                            max_value=700,
                            min_clamped=True,
                            max_clamped=True,
                            width=-1,
                            callback=self.on_ui_setting_changed,
                        )
                        dpg.add_text(self.t("rounding"), tag="ui_rounding_label")
                        self.add_linked_float_control(
                            slider_tag="ui_rounding_slider",
                            input_tag="ui_rounding_input",
                            default_value=float(self.ui_config["ui_rounding"]),
                            min_value=0.0,
                            max_value=18.0,
                            callback=self.on_ui_setting_changed,
                            format="%.1f",
                        )

                with self.subsection_header(label=self.t("section_marker_preview"), default_open=False, indent=18, tag="header_marker_preview"):
                    with self.subsection_panel():
                        dpg.add_text(self.t("preview_alpha"), tag="ui_preview_alpha_label")
                        self.add_linked_int_control(
                            slider_tag="ui_preview_alpha_slider",
                            input_tag="ui_preview_alpha_input",
                            default_value=int(self.ui_config["preview_point_alpha"]),
                            min_value=20,
                            max_value=255,
                            callback=self.on_ui_setting_changed,
                        )
                        dpg.add_text(self.t("preview_radius_small"), tag="ui_preview_radius_small_label")
                        self.add_linked_float_control(
                            slider_tag="ui_preview_radius_small_slider",
                            input_tag="ui_preview_radius_small_input",
                            default_value=float(self.ui_config["preview_point_radius_small"]),
                            min_value=0.6,
                            max_value=4.0,
                            callback=self.on_ui_setting_changed,
                            format="%.2f",
                        )
                        dpg.add_text(self.t("preview_radius_big"), tag="ui_preview_radius_big_label")
                        self.add_linked_float_control(
                            slider_tag="ui_preview_radius_big_slider",
                            input_tag="ui_preview_radius_big_input",
                            default_value=float(self.ui_config["preview_point_radius_big"]),
                            min_value=0.8,
                            max_value=8.0,
                            callback=self.on_ui_setting_changed,
                            format="%.2f",
                        )

                with self.subsection_header(label=self.t("section_colors"), default_open=False, indent=18, tag="header_colors"):
                    with self.subsection_panel():
                        dpg.add_text(self.t("background_color"), tag="ui_background_color_label")
                        dpg.add_color_edit(
                            tag="ui_bg_color_input",
                            default_value=self.ui_config["ui_bg_color"],
                            alpha_bar=False,
                            width=-1,
                            callback=self.on_ui_setting_changed,
                        )
                        dpg.add_text(self.t("panel_color"), tag="ui_panel_color_label")
                        dpg.add_color_edit(
                            tag="ui_panel_color_input",
                            default_value=self.ui_config["ui_panel_color"],
                            alpha_bar=False,
                            width=-1,
                            callback=self.on_ui_setting_changed,
                        )
                        dpg.add_text(self.t("frame_color"), tag="ui_frame_color_label")
                        dpg.add_color_edit(
                            tag="ui_frame_color_input",
                            default_value=self.ui_config["ui_frame_color"],
                            alpha_bar=False,
                            width=-1,
                            callback=self.on_ui_setting_changed,
                        )
                        dpg.add_text(self.t("accent_color"), tag="ui_accent_color_label")
                        dpg.add_color_edit(
                            tag="ui_accent_color_input",
                            default_value=self.ui_config["ui_accent_color"],
                            alpha_bar=False,
                            width=-1,
                            callback=self.on_ui_setting_changed,
                        )

                dpg.add_button(label=self.t("save_ui_config"), tag="save_ui_config_button", width=-1, callback=lambda *_: self.save_ui_config())

    def build_help_tab(self) -> None:
        with dpg.tab(label=self.t("tab_help"), tag="tab_help"):
            with dpg.collapsing_header(label=self.t("section_controls"), default_open=True, tag="header_controls"):
                dpg.add_text(self.t("help_title"), color=(255, 221, 120), tag="help_title_text")
                dpg.add_text(self.t("control_pan"), tag="help_control_pan_text")
                dpg.add_text(self.t("control_zoom"), tag="help_control_zoom_text")
                dpg.add_text(self.t("control_select"), tag="help_control_select_text")
                dpg.add_text(self.t("control_delete"), tag="help_control_delete_text")
                dpg.add_text(self.t("control_delete_image"), tag="help_control_delete_image_text")
                dpg.add_text(self.t("control_hide"), tag="help_control_hide_text")
                dpg.add_text(self.t("control_undo"), tag="help_control_undo_text")

            with dpg.collapsing_header(label=self.t("section_notes"), default_open=False, tag="header_notes"):
                dpg.add_text(self.t("help_note_parse"), tag="help_note_parse_text")
                dpg.add_text(self.t("help_note_layers"), tag="help_note_layers_text")
                dpg.add_text(self.t("help_note_ui"), tag="help_note_ui_text")

    def create_ui(self) -> None:
        dpg.create_context()
        with dpg.texture_registry(tag="texture_registry"):
            pass

        with dpg.window(tag="main_window", label=self.t("app_title")):
            with dpg.group(horizontal=True):
                with dpg.child_window(tag="sidebar", width=int(self.ui_config["sidebar_width"]), border=True):
                    dpg.add_text(self.t("app_title"), tag="app_title_text", color=(245, 245, 245))
                    dpg.add_spacer(height=6)
                    with dpg.child_window(
                        tag="sidebar_content",
                        height=-108,
                        border=False,
                    ):
                        with dpg.tab_bar(tag="sidebar_tabs"):
                            self.build_main_tab()
                            self.build_image_tab()
                            self.build_layers_tab()
                            self.build_settings_tab()
                            self.build_help_tab()

                    dpg.add_separator()
                    with dpg.child_window(
                        tag="sidebar_footer",
                        height=78,
                        border=False,
                        no_scrollbar=True,
                    ):
                        dpg.add_text(self.t("status_ready"), tag="status_text", wrap=320)
                        dpg.add_text(self.t("progress_zero"), tag="progress_text", wrap=320)
                        dpg.add_text(self.t("zoom_label", scale=1.0), tag="zoom_text")

                with dpg.child_window(tag="sidebar_resize_grip", width=10, border=False, no_scrollbar=True):
                    dpg.add_spacer(height=1)

                with dpg.child_window(tag="viewer_panel", width=-1, height=-1, border=False, no_scrollbar=True):
                    with dpg.drawlist(tag="map_drawlist", width=100, height=100):
                        pass

        with dpg.handler_registry():
            dpg.add_mouse_wheel_handler(callback=self.on_mouse_wheel)
            dpg.add_key_press_handler(callback=self.on_key_press)

        self.configure_image_settings_visibility()
        self.update_image_marker_estimate(None)
        self.create_onboarding_modal()
        self.refresh_language_settings_ui()
        
        # Установка иконки для таскбара и топбара
        try:
            if hasattr(dpg, 'set_viewport_icon'):
                icon_path = str(RESOURCE_ROOT / "assets" / "app.ico")
                dpg.set_viewport_icon(icon_path)
        except:
            pass

        dpg.create_viewport(title=self.t("app_title"), width=1440, height=900)
        self.setup_fonts()
        dpg.setup_dearpygui()
        self.apply_ui_theme()
        self.refresh_exbo_settings_ui()
        self.refresh_language_settings_ui()
        dpg.show_viewport()
        self.set_app_icon()
        dpg.set_primary_window("main_window", True)
        dpg.maximize_viewport()
        self.apply_ui_theme()
        self.refresh_exbo_settings_ui()
        self.refresh_language_settings_ui()
        if (self.language_setup_required or self.exbo_setup_required) and dpg.does_item_exist("onboarding_modal"):
            self.show_centered_modal("onboarding_modal", 620, 300)
            
    def set_app_icon(self):
        """Установка иконки приложения через Windows API"""
        try:
            # Получаем handle окна после показа вьюпорта
            hwnd = ctypes.windll.user32.FindWindowW(None, "Waypoint Editor")
            if not hwnd:
                hwnd = ctypes.windll.user32.GetActiveWindow()
            # Путь к иконке
            icon_path = str(RESOURCE_ROOT / "assets" / "app.ico")
            # Загружаем иконку через LoadImage
            hicon = ctypes.windll.user32.LoadImageW(
                None, 
                icon_path, 
                1,  # IMAGE_ICON
                0,   # Ширина (0 = по умолчанию)
                0,   # Высота (0 = по умолчанию)
                0x00000010  # LR_LOADFROMFILE
            )
            if hicon:
                # Устанавливаем иконку для окна
                ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hicon)  # WM_SETICON
                ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, hicon)  # WM_SETICON для таскбара
        except Exception as e:
            print(f"Failed to set app icon: {e}")
            pass
