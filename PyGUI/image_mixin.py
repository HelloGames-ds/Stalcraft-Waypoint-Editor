from __future__ import annotations

import math
from pathlib import Path
from tkinter import Tk, filedialog

import dearpygui.dearpygui as dpg
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from app_constants import (
    DEFAULT_ALPHA_CUTOFF,
    DEFAULT_IMAGE_BLUR_RADIUS,
    DEFAULT_IMAGE_CONTRAST,
    DEFAULT_IMAGE_MASK_GROW_SHRINK,
    DEFAULT_IMAGE_NOISE_CLEANUP,
    DEFAULT_BRIGHTNESS_CUTOFF,
    DEFAULT_CONTOUR_EDGE_THRESHOLD,
    DEFAULT_CONTOUR_THICKNESS,
    DEFAULT_IMAGE_RESOLUTION,
    IMAGE_AUTO_RESOLUTION_MAX_DIM,
    IMAGE_PREVIEW_HANDLE_SCREEN_PX,
    IMAGE_PREVIEW_MIN_SIZE_MAP_PX,
    IMAGE_PREVIEW_TEXTURE_MAX_DIM,
    PROJECT_ROOT,
)
from simplemapper_core import WAYPOINT_ICON_NAMES


class ImageGenerationMixin:
    def get_current_image_parser_mode(self) -> str:
        mode = getattr(self, "image_parser_mode", "fill")
        if mode not in {"fill", "silhouette", "detail_edges"}:
            return "fill"
        return mode

    def schedule_image_marker_preview_refresh(self) -> None:
        self.image_preview_marker_cache_dirty = True
        self.needs_redraw = True

    def flush_image_marker_preview_refresh(self) -> None:
        if not self.image_preview_marker_cache_dirty:
            return
        self.image_preview_marker_cache_dirty = False
        self.invalidate_image_marker_preview()

    def invalidate_image_marker_preview(self) -> None:
        self.image_preview_marker_cache_dirty = False
        self.image_preview_marker_cache_key = None
        self.image_preview_marker_cache_points = []
        self.image_preview_marker_cache_size = (0, 0)
        self.needs_redraw = True

    def update_image_marker_estimate(self, count: int | None = None) -> None:
        if not dpg.does_item_exist("image_marker_estimate_text"):
            return
        if count is None:
            dpg.set_value("image_marker_estimate_text", self.t("estimated_markers_empty"))
        else:
            dpg.set_value("image_marker_estimate_text", self.t("estimated_markers", count=count))

    def configure_image_settings_visibility(self) -> None:
        parser_mode = self.get_current_image_parser_mode()
        contour_mode = parser_mode in {"silhouette", "detail_edges"}
        include_background = bool(dpg.get_value("image_include_background_input")) if dpg.does_item_exist("image_include_background_input") else False
        if dpg.does_item_exist("header_contour"):
            dpg.configure_item("header_contour", show=contour_mode)
        for tag in (
            "image_brightness_cutoff_label",
            "image_brightness_cutoff_slider",
            "image_brightness_cutoff_input",
        ):
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, show=contour_mode)
        for tag in (
            "image_contour_edge_threshold_label",
            "image_contour_edge_threshold_slider",
            "image_contour_edge_threshold_input",
            "image_contour_thickness_label",
            "image_contour_thickness_slider",
            "image_contour_thickness_input",
            "image_contour_help_text",
        ):
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, show=contour_mode)
        for tag in ("image_alpha_cutoff_label", "image_alpha_cutoff_slider", "image_alpha_cutoff_input"):
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, show=not include_background)

    def on_image_settings_changed(self, sender=None, app_data=None, user_data=None) -> None:
        self.configure_image_settings_visibility()
        self.invalidate_image_marker_preview()
        if not self.image_path:
            self.update_image_marker_estimate(None)

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

    def remove_loaded_image(self) -> None:
        had_image = bool(self.image_path or self.image_preview_bounds_map is not None)
        self.clear_image_preview()
        self.image_path = ""
        if dpg.does_item_exist("image_path_input"):
            dpg.set_value("image_path_input", "")
        if had_image:
            self.update_generated_status(self.t("status_image_removed"))

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

    def preprocess_marker_source_image(self, source_rgba: Image.Image) -> Image.Image:
        image = source_rgba.convert("RGBA")
        blur_radius = float(dpg.get_value("image_blur_radius_input")) if dpg.does_item_exist("image_blur_radius_input") else DEFAULT_IMAGE_BLUR_RADIUS
        contrast = float(dpg.get_value("image_contrast_input")) if dpg.does_item_exist("image_contrast_input") else DEFAULT_IMAGE_CONTRAST

        if blur_radius > 0.001:
            image = image.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        if abs(contrast - 1.0) > 1e-3:
            rgb = ImageEnhance.Contrast(image.convert("RGB")).enhance(contrast)
            alpha = image.getchannel("A")
            image = rgb.convert("RGBA")
            image.putalpha(alpha)
        return image

    def apply_mask_noise_cleanup(self, mask: np.ndarray, min_neighbors: int) -> np.ndarray:
        if min_neighbors <= 0 or mask.size == 0:
            return mask

        padded = np.pad(mask, 1, constant_values=False)
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
        neighbor_count = np.zeros(mask.shape, dtype=np.uint8)
        for item in neighbors:
            neighbor_count += item.astype(np.uint8)
        return mask & (neighbor_count >= min_neighbors)

    def apply_mask_growth_shrink(self, mask: np.ndarray, grow_steps: int) -> np.ndarray:
        if grow_steps == 0 or mask.size == 0:
            return mask

        result = mask.copy()
        for _ in range(abs(grow_steps)):
            padded = np.pad(result, 1, constant_values=False)
            neighborhood = [
                padded[1:-1, 1:-1],
                padded[:-2, 1:-1],
                padded[2:, 1:-1],
                padded[1:-1, :-2],
                padded[1:-1, 2:],
                padded[:-2, :-2],
                padded[:-2, 2:],
                padded[2:, :-2],
                padded[2:, 2:],
            ]
            if grow_steps > 0:
                result = np.logical_or.reduce(neighborhood)
            else:
                result = np.logical_and.reduce(neighborhood)
        return result

    def compute_binary_boundary_mask(self, mask: np.ndarray) -> np.ndarray:
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
        return center & (~np.logical_and.reduce(neighbors))

    def compute_max_neighbor_delta(self, channel: np.ndarray) -> np.ndarray:
        padded = np.pad(channel.astype(np.float32), 1, mode="edge")
        center = padded[1:-1, 1:-1]
        deltas = [
            np.abs(center - padded[:-2, 1:-1]),
            np.abs(center - padded[2:, 1:-1]),
            np.abs(center - padded[1:-1, :-2]),
            np.abs(center - padded[1:-1, 2:]),
            np.abs(center - padded[:-2, :-2]),
            np.abs(center - padded[:-2, 2:]),
            np.abs(center - padded[2:, :-2]),
            np.abs(center - padded[2:, 2:]),
        ]
        return np.maximum.reduce(deltas)

    def build_image_mask(self, rgba_data: np.ndarray) -> np.ndarray:
        alpha_cutoff = max(0, min(255, int(dpg.get_value("image_alpha_cutoff_input"))))
        brightness_cutoff = max(0, min(255, int(dpg.get_value("image_brightness_cutoff_input"))))
        include_background = bool(dpg.get_value("image_include_background_input")) if dpg.does_item_exist("image_include_background_input") else False
        grow_shrink = int(dpg.get_value("image_mask_grow_shrink_input")) if dpg.does_item_exist("image_mask_grow_shrink_input") else DEFAULT_IMAGE_MASK_GROW_SHRINK
        noise_cleanup = int(dpg.get_value("image_noise_cleanup_input")) if dpg.does_item_exist("image_noise_cleanup_input") else DEFAULT_IMAGE_NOISE_CLEANUP

        if include_background:
            mask = np.ones((rgba_data.shape[0], rgba_data.shape[1]), dtype=bool)
        else:
            alpha = rgba_data[:, :, 3]
            mask = alpha >= alpha_cutoff
        if brightness_cutoff > 0:
            rgb = rgba_data[:, :, :3].astype(np.float32)
            brightness = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]).astype(np.uint8)
            mask &= brightness >= brightness_cutoff
        mask = self.apply_mask_noise_cleanup(mask, noise_cleanup)
        mask = self.apply_mask_growth_shrink(mask, grow_shrink)
        return mask

    def extract_contour_mask(self, mask: np.ndarray, rgba_data: np.ndarray, thickness: int) -> np.ndarray:
        if mask.size == 0:
            return mask

        edge_threshold = max(
            0,
            min(
                255,
                int(dpg.get_value("image_contour_edge_threshold_input"))
                if dpg.does_item_exist("image_contour_edge_threshold_input")
                else DEFAULT_CONTOUR_EDGE_THRESHOLD,
            ),
        )
        include_background = bool(dpg.get_value("image_include_background_input")) if dpg.does_item_exist("image_include_background_input") else False
        noise_cleanup = int(dpg.get_value("image_noise_cleanup_input")) if dpg.does_item_exist("image_noise_cleanup_input") else DEFAULT_IMAGE_NOISE_CLEANUP

        rgb = rgba_data[:, :, :3].astype(np.float32)
        luminance = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
        alpha = rgba_data[:, :, 3].astype(np.float32)
        lum_delta = self.compute_max_neighbor_delta(luminance)
        alpha_delta = self.compute_max_neighbor_delta(alpha)
        edge_strength = np.maximum(lum_delta, alpha_delta)

        boundary = self.compute_binary_boundary_mask(mask)
        if include_background:
            result = edge_strength >= edge_threshold
            if noise_cleanup > 0:
                result = self.apply_mask_noise_cleanup(result, min(8, max(1, noise_cleanup)))
        else:
            # Keep contour mode focused on the silhouette of the built mask
            # instead of every internal texture change inside the image.
            edge_band = self.apply_mask_growth_shrink(boundary, 2)
            threshold_edges = edge_band & (edge_strength >= edge_threshold)
            result = boundary | threshold_edges
            if noise_cleanup > 0:
                result = self.apply_mask_noise_cleanup(result, min(8, max(1, noise_cleanup)))
            result &= self.apply_mask_growth_shrink(mask, max(1, thickness + 1))

        if not np.any(result):
            result = boundary
        if thickness > 1:
            result = self.apply_mask_growth_shrink(result, thickness - 1)
        if not include_background:
            result &= self.apply_mask_growth_shrink(mask, max(1, thickness + 1))
        return result

    def extract_detail_edge_mask(self, mask: np.ndarray, rgba_data: np.ndarray, thickness: int) -> np.ndarray:
        if mask.size == 0:
            return mask

        edge_threshold = max(
            0,
            min(
                255,
                int(dpg.get_value("image_contour_edge_threshold_input"))
                if dpg.does_item_exist("image_contour_edge_threshold_input")
                else DEFAULT_CONTOUR_EDGE_THRESHOLD,
            ),
        )
        include_background = bool(dpg.get_value("image_include_background_input")) if dpg.does_item_exist("image_include_background_input") else False
        noise_cleanup = int(dpg.get_value("image_noise_cleanup_input")) if dpg.does_item_exist("image_noise_cleanup_input") else DEFAULT_IMAGE_NOISE_CLEANUP

        rgb = rgba_data[:, :, :3].astype(np.float32)
        luminance = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
        alpha = rgba_data[:, :, 3].astype(np.float32)
        edge_strength = np.maximum(
            self.compute_max_neighbor_delta(luminance),
            self.compute_max_neighbor_delta(alpha),
        )
        result = edge_strength >= edge_threshold
        if not include_background:
            result &= self.apply_mask_growth_shrink(mask, max(1, thickness + 1))
        if noise_cleanup > 0:
            result = self.apply_mask_noise_cleanup(result, min(8, max(1, noise_cleanup)))
        if thickness > 1:
            result = self.apply_mask_growth_shrink(result, thickness - 1)
        return result

    def build_parser_mask(self, rgba_data: np.ndarray, parser_mode: str, contour_thickness: int) -> np.ndarray:
        base_mask = self.build_image_mask(rgba_data)
        if parser_mode == "silhouette":
            return self.extract_contour_mask(base_mask, rgba_data, contour_thickness)
        if parser_mode == "detail_edges":
            return self.extract_detail_edge_mask(base_mask, rgba_data, contour_thickness)
        return base_mask

    def collect_marker_pixels(
        self,
        rgba_data: np.ndarray,
        mask: np.ndarray,
        max_markers: int,
        sampling_step: int = 1,
    ) -> list[tuple[int, int, int, int, int]]:
        height, width = mask.shape
        total_pixels = int(np.count_nonzero(mask))
        if total_pixels == 0:
            return []

        step = max(1, int(sampling_step))
        if total_pixels > max_markers:
            step = max(step, int(math.ceil(math.sqrt(total_pixels / max_markers))))

        pixels: list[tuple[int, int, int, int, int]] = []
        for y0 in range(0, height, step):
            y1 = min(height, y0 + step)
            for x0 in range(0, width, step):
                x1 = min(width, x0 + step)
                sub_mask = mask[y0:y1, x0:x1]
                if not np.any(sub_mask):
                    continue

                ys, xs = np.nonzero(sub_mask)
                mean_y = float(np.mean(ys))
                mean_x = float(np.mean(xs))
                centroid_index = int(np.argmin((ys - mean_y) ** 2 + (xs - mean_x) ** 2))
                py = y0 + int(ys[centroid_index])
                px = x0 + int(xs[centroid_index])

                sub_pixels = rgba_data[y0:y1, x0:x1][sub_mask]
                avg_rgb = np.round(np.mean(sub_pixels[:, :3], axis=0)).astype(int)
                pixels.append(
                    (
                        px,
                        py,
                        int(avg_rgb[0]),
                        int(avg_rgb[1]),
                        int(avg_rgb[2]),
                    )
                )

        if len(pixels) > max_markers:
            stride = len(pixels) / max_markers
            pixels = [pixels[min(len(pixels) - 1, int(index * stride))] for index in range(max_markers)]
        return pixels

    def get_marker_preview_data(self) -> tuple[list[tuple[int, int, int, int, int]], int, int]:
        if not self.image_path:
            self.update_image_marker_estimate(None)
            return [], 0, 0

        candidate = Path(self.image_path)
        if not candidate.exists():
            self.update_image_marker_estimate(None)
            return [], 0, 0

        parser_mode = self.get_current_image_parser_mode()
        contour_thickness = max(1, min(8, int(dpg.get_value("image_contour_thickness_input"))))
        contour_edge_threshold = max(0, min(255, int(dpg.get_value("image_contour_edge_threshold_input")))) if dpg.does_item_exist("image_contour_edge_threshold_input") else DEFAULT_CONTOUR_EDGE_THRESHOLD
        sampling_step = max(1, min(32, int(dpg.get_value("image_sampling_step_input"))))
        max_markers = max(1, min(100000, int(dpg.get_value("image_marker_limit_input"))))
        include_background = bool(dpg.get_value("image_include_background_input")) if dpg.does_item_exist("image_include_background_input") else False
        contrast = float(dpg.get_value("image_contrast_input")) if dpg.does_item_exist("image_contrast_input") else DEFAULT_IMAGE_CONTRAST
        blur_radius = float(dpg.get_value("image_blur_radius_input")) if dpg.does_item_exist("image_blur_radius_input") else DEFAULT_IMAGE_BLUR_RADIUS
        grow_shrink = int(dpg.get_value("image_mask_grow_shrink_input")) if dpg.does_item_exist("image_mask_grow_shrink_input") else DEFAULT_IMAGE_MASK_GROW_SHRINK
        noise_cleanup = int(dpg.get_value("image_noise_cleanup_input")) if dpg.does_item_exist("image_noise_cleanup_input") else DEFAULT_IMAGE_NOISE_CLEANUP
        preview_bounds_key = None
        if self.image_preview_bounds_map is not None:
            preview_bounds_key = tuple(round(float(v), 2) for v in self.image_preview_bounds_map)
        cache_key = (
            str(candidate),
            candidate.stat().st_mtime_ns,
            parser_mode,
            contour_thickness,
            contour_edge_threshold,
            sampling_step,
            include_background,
            round(contrast, 3),
            round(blur_radius, 3),
            grow_shrink,
            noise_cleanup,
            preview_bounds_key,
            int(dpg.get_value("image_alpha_cutoff_input")),
            int(dpg.get_value("image_brightness_cutoff_input")),
            max_markers,
        )

        if self.image_preview_marker_cache_key == cache_key:
            self.update_image_marker_estimate(len(self.image_preview_marker_cache_points))
            w, h = self.image_preview_marker_cache_size
            return list(self.image_preview_marker_cache_points), w, h

        if self.image_preview_drag_mode is not None and self.image_preview_marker_cache_points:
            self.update_image_marker_estimate(len(self.image_preview_marker_cache_points))
            w, h = self.image_preview_marker_cache_size
            return list(self.image_preview_marker_cache_points), w, h

        try:
            with Image.open(candidate) as source_image:
                source_rgba = self.preprocess_marker_source_image(source_image.convert("RGBA"))
                base_w, base_h = self.get_auto_image_resolution(source_rgba.width, source_rgba.height)
                image = source_rgba.resize((base_w, base_h), Image.Resampling.LANCZOS)
        except Exception:
            self.update_image_marker_estimate(None)
            return [], 0, 0

        data = np.asarray(image, dtype=np.uint8)
        mask = self.build_parser_mask(data, parser_mode, contour_thickness)

        max_markers = self.get_effective_max_markers(mask)
        image = self.prepare_marker_source_image(
            image,
            max_markers,
            parser_mode=parser_mode,
            contour_thickness=contour_thickness,
        )
        data = np.asarray(image, dtype=np.uint8)
        mask = self.build_parser_mask(data, parser_mode, contour_thickness)
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

    def prepare_marker_source_image(
        self,
        source_rgba: Image.Image,
        max_markers: int,
        parser_mode: str = "fill",
        contour_thickness: int = 1,
    ) -> Image.Image:
        target_w, target_h = self.get_auto_image_resolution(source_rgba.width, source_rgba.height)
        image = source_rgba.resize((target_w, target_h), Image.Resampling.LANCZOS)

        while True:
            data = np.asarray(image, dtype=np.uint8)
            mask = self.build_parser_mask(data, parser_mode, contour_thickness)
            marker_count = int(np.count_nonzero(mask))
            if marker_count <= max_markers or image.width <= 8 or image.height <= 8:
                return image

            scale = math.sqrt(max_markers / max(marker_count, 1))
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
        self.schedule_image_marker_preview_refresh()
        self.needs_redraw = True

    def apply_optimization_settings(self) -> None:
        self.max_markers_on_screen = max(1, int(dpg.get_value("marker_screen_limit_input")))
        self.square_render_threshold = max(1, int(dpg.get_value("marker_square_threshold_input")))
        self.settings_config["max_markers_on_screen"] = int(self.max_markers_on_screen)
        self.settings_config["square_render_threshold"] = int(self.square_render_threshold)
        self.save_settings_config()
        self.sync_optimization_settings_ui()
        self.overlay_cache_key = None
        self.needs_redraw = True
        self.set_status(
            self.t(
                "status_optimization_applied",
                screen=self.max_markers_on_screen,
                squares=self.square_render_threshold,
            )
        )

    def load_image_from_path(self, path: str) -> None:
        path = path.strip()
        if not path:
            return
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = (PROJECT_ROOT / candidate).resolve()
        if not candidate.exists():
            self.set_status(self.t("status_image_not_found", path=candidate))
            return
        self.image_path = str(candidate)
        if dpg.does_item_exist("image_path_input"):
            dpg.set_value("image_path_input", self.image_path)
        try:
            self.load_image_preview_texture(candidate)
        except Exception as error:
            self.set_status(self.t("status_image_preview_load_error", error=error))
            return
        self.invalidate_image_marker_preview()
        self.configure_image_settings_visibility()
        self.reset_image_preview_bounds()
        auto_w, auto_h = self.get_auto_image_resolution(*self.image_preview_source_size)
        self.update_generated_status(self.t("source_info", name=candidate.name, width=auto_w, height=auto_h))
        self.needs_redraw = True

    def reload_current_image(self) -> None:
        if not self.image_path:
            self.set_status(self.t("status_select_image_first"))
            return
        self.load_image_from_path(self.image_path)

    def generate_markers_from_image(self) -> None:
        if not self.image_path:
            self.update_generated_status(self.t("status_select_image_first"))
            return
        if self.active_map is None:
            self.update_generated_status(self.t("status_open_map_first"))
            return
        if self.image_preview_bounds_map is None:
            self.update_generated_status(self.t("status_place_image_first"))
            return

        fixed_icon_index = max(0, min(6, int(dpg.get_value("image_icon_input"))))
        use_auto_icons = bool(dpg.get_value("image_auto_icons_input"))
        parser_mode = self.get_current_image_parser_mode()
        opaque_pixels, target_w, target_h = self.get_marker_preview_data()

        if not opaque_pixels:
            self.update_generated_status(self.t("status_no_pixels_after_cutoff"))
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
        self.generated_raw_waypoints = []
        self.raw_waypoints.extend(generated)
        self.sync_waypoints_from_raw()
        self.clear_image_preview()
        self.update_generated_status(
            self.t(
                "status_generated",
                count=len(generated),
                width=target_w,
                height=target_h,
                mode=self.get_image_parser_mode_label(parser_mode),
            )
        )

    def clear_generated_waypoints(self) -> None:
        if not self.generated_raw_waypoints:
            return
        self.push_undo_state()
        self.generated_raw_waypoints = []
        self.sync_waypoints_from_raw()
        self.update_generated_status(self.t("status_generation_buffer_cleared"))

    def bake_generated_waypoints(self) -> None:
        if not self.generated_raw_waypoints:
            self.update_generated_status(self.t("status_generation_buffer_empty"))
            return
        self.push_undo_state()
        baked_count = len(self.generated_raw_waypoints)
        self.raw_waypoints.extend(self.generated_raw_waypoints)
        self.generated_raw_waypoints = []
        self.sync_waypoints_from_raw()
        self.update_generated_status(self.t("status_baked", count=baked_count))

    def on_image_picked(self, sender, app_data, user_data=None) -> None:
        file_path = app_data.get("file_path_name")
        if file_path:
            self.load_image_from_path(file_path)

    def on_open_image_clicked(self, sender, app_data, user_data) -> None:
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        file_path = filedialog.askopenfilename(
            title=self.t("browse_image_title"),
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

    def on_reload_image_clicked(self, sender, app_data, user_data) -> None:
        self.reload_current_image()

    def on_clear_generated_clicked(self, sender, app_data, user_data) -> None:
        self.clear_generated_waypoints()

    def on_bake_generated_clicked(self, sender, app_data, user_data) -> None:
        self.bake_generated_waypoints()

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
            fill=(255, 255, 255, 26),
            color=(0, 0, 0, 0),
            parent=draw_tag,
        )

        preview_pixels, target_w, target_h = self.get_marker_preview_data()
        if target_w > 0 and target_h > 0 and preview_pixels:
            preview_w = max(1.0, x2 - x1)
            preview_h = max(1.0, y2 - y1)
            preview_alpha = int(self.ui_config["preview_point_alpha"])
            point_radius = float(self.ui_config["preview_point_radius_small"])
            if len(preview_pixels) < 2500:
                point_radius = float(self.ui_config["preview_point_radius_big"])

            for px, py, r, g, b in preview_pixels:
                map_x = x1 + ((px + 0.5) / target_w) * preview_w
                map_y = y1 + ((py + 0.5) / target_h) * preview_h
                screen_x, screen_y = self.map_to_screen(map_x, map_y)
                dpg.draw_circle(
                    (screen_x, screen_y),
                    radius=point_radius,
                    color=(r, g, b, preview_alpha),
                    fill=(r, g, b, preview_alpha),
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
