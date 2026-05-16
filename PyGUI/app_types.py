from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TextureInfo:
    tag: str
    width: int
    height: int
    map_x: float
    map_y: float
