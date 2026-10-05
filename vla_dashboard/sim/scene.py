"""Scene shared by the physics simulators (PyBullet, MuJoCo): table, objects, labels,
camera and robot placement. Keeping it in one place guarantees both engines build the
same world, so perception, the learned policy and the GUI behave identically on either."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .simulator import TABLE_X, TABLE_Y

TABLE_TOP_Z = 0.0
# Robot stands on the table at the back-right corner, like the reference scene.
BASE_POS = (0.30, 0.80, TABLE_TOP_Z)
BASE_YAW = math.atan2(0.55 - BASE_POS[1], 0.0 - BASE_POS[0])  # face the middle of the table
CAMERA = dict(eye=(-0.42, -0.78, 1.18), target=(0.08, 0.58, 0.30), fov_deg=58.0)
HOME_EE = np.array([0.05, 0.55, 0.30])
# Brighter than the CAD colour so it reads like the reference image under TinyRenderer lighting.
RENDER_BLUE = (0.16, 0.34, 0.86, 1.0)


@dataclass(frozen=True)
class ObjSpec:
    name: str
    kind: str
    rgba: tuple[float, float, float, float]
    size: float
    height: float
    xy: tuple[float, float]


OBJECTS = (
    ObjSpec("cube", "cube", (0.86, 0.12, 0.12, 1), 0.05, 0.05, (-0.22, 0.46)),
    ObjSpec("cylinder", "cylinder", (0.14, 0.18, 0.84, 1), 0.05, 0.06, (-0.05, 0.46)),
    ObjSpec("sphere", "sphere", (0.16, 0.78, 0.28, 1), 0.05, 0.05, (0.12, 0.46)),
)


def _label_rects() -> list[tuple[str, tuple[float, float, float, float]]]:
    """World-space rectangles (x0, y0, x1, y1) of the printed labels in front of each object."""
    out = []
    for o in OBJECTS:
        w = 0.016 * len(o.name) + 0.02
        cx, cy = o.xy[0], o.xy[1] - 0.08
        out.append((o.name.upper(), (cx - w / 2, cy - 0.02, cx + w / 2, cy + 0.02)))
    return out


def _table_texture(path: Path, px_per_m: int = 1400) -> None:
    w = int((TABLE_X[1] - TABLE_X[0]) * px_per_m)
    h = int((TABLE_Y[1] - TABLE_Y[0]) * px_per_m)
    img = np.full((h, w, 3), (128, 128, 132), np.uint8)
    for text, (x0, y0, x1, y1) in _label_rects():
        u0, u1 = int((x0 - TABLE_X[0]) * px_per_m), int((x1 - TABLE_X[0]) * px_per_m)
        # image row 0 = far edge (max y) so the text reads upright from the camera
        v0, v1 = int((TABLE_Y[1] - y1) * px_per_m), int((TABLE_Y[1] - y0) * px_per_m)
        cv2.rectangle(img, (u0, v0), (u1, v1), (240, 240, 235), -1)
        scale = (v1 - v0) * 0.026
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 3)
        scale *= min(1.0, 0.9 * (u1 - u0) / tw)
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 3)
        cv2.putText(img, text, ((u0 + u1 - tw) // 2, (v0 + v1 + th) // 2), cv2.FONT_HERSHEY_SIMPLEX, scale,
                    (20, 20, 20), 3, cv2.LINE_AA)
    cv2.imwrite(str(path), img[:, :, ::-1])


def _gradient(h: int, w: int) -> np.ndarray:
    g = np.linspace(226, 172, h, dtype=np.float32)[:, None, None]
    return np.broadcast_to(g, (h, w, 3)).astype(np.uint8)
