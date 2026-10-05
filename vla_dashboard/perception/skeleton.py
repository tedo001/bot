"""Skeleton view.

Two skeletons are drawn:

* Object skeletons: the medial axis of each RF-DETR mask, computed with a pure
  OpenCV morphological skeleton (works with opencv-python-headless, no extra
  dependency). Each mask is cropped to its box first, so cost scales with object
  size, not frame size.
* Robot skeleton: the arm's joint chain projected into the image (from the
  simulator's kinematics, or from a pose/keypoint model on real hardware).
"""

from __future__ import annotations

import cv2
import numpy as np

from ..schemas import Detection

_KERNEL = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))


def morphological_skeleton(mask: np.ndarray, max_iter: int = 64) -> np.ndarray:
    """Lantuéjoul skeleton of a binary mask. Returns a uint8 {0,255} image of the same shape."""
    img = (mask > 0).astype(np.uint8) * 255
    skel = np.zeros_like(img)
    for _ in range(max_iter):
        eroded = cv2.erode(img, _KERNEL)
        opened = cv2.dilate(eroded, _KERNEL)
        skel |= cv2.subtract(img, opened)
        img = eroded
        if not cv2.countNonZero(img):
            break
    return skel


def object_skeletons(dets: list[Detection], masks: np.ndarray) -> np.ndarray:
    """Union of per-object skeletons as an (H, W) uint8 image."""
    if masks.shape[0] == 0:
        return np.zeros(masks.shape[1:], np.uint8)
    h, w = masks.shape[1:]
    out = np.zeros((h, w), np.uint8)
    for det, m in zip(dets, masks):
        b = det.box
        x1, y1 = max(0, int(b.x1) - 1), max(0, int(b.y1) - 1)
        x2, y2 = min(w, int(b.x2) + 1), min(h, int(b.y2) + 1)
        if x2 > x1 and y2 > y1:
            out[y1:y2, x1:x2] |= morphological_skeleton(m[y1:y2, x1:x2])
    return out
