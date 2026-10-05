"""Overlay compositing (runs in the control thread at display rate, never in the GUI thread)."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ..perception.pipeline import PerceptionOutput

_PALETTE = np.array([(255, 99, 71), (65, 105, 225), (50, 205, 50), (255, 165, 0), (186, 85, 211),
                     (0, 206, 209)], dtype=np.float32)


@dataclass
class OverlayFlags:
    """Plain bools written by the GUI thread and read by the control thread. Single
    attribute reads/writes are atomic under the GIL, so no lock is needed."""

    boxes: bool = True
    masks: bool = True
    skeleton: bool = True
    ocr: bool = True
    hud: bool = True


def compose(rgb: np.ndarray, perc: PerceptionOutput | None, flags: OverlayFlags, hud: str = "") -> np.ndarray:
    """Return a NEW array with overlays; the source frame stays untouched (it is shared)."""
    out = rgb.copy()
    if perc is None:
        return out
    if flags.masks and perc.masks.shape[0]:
        for i, m in enumerate(perc.masks):
            if m.shape != out.shape[:2]:
                continue
            col = _PALETTE[i % len(_PALETTE)]
            out[m] = (out[m] * 0.45 + col * 0.55).astype(np.uint8)
    if flags.skeleton:
        if perc.skeleton is not None and perc.skeleton.shape == out.shape[:2]:
            out[cv2.dilate(perc.skeleton, None) > 0] = (255, 0, 255)
        sk = perc.robot_skeleton_2d
        if sk is not None:
            pts = sk.astype(np.int32)
            for a, b in zip(pts[:-1], pts[1:]):
                cv2.line(out, tuple(a), tuple(b), (255, 140, 0), 2, cv2.LINE_AA)
            for p in pts:
                cv2.circle(out, tuple(p), 5, (255, 220, 0), -1, cv2.LINE_AA)
                cv2.circle(out, tuple(p), 5, (60, 30, 0), 1, cv2.LINE_AA)
    if flags.boxes:
        for obj in perc.summary.objects:
            b = obj.box
            p1, p2 = (int(b.x1), int(b.y1)), (int(b.x2), int(b.y2))
            cv2.rectangle(out, p1, p2, (0, 255, 255), 1, cv2.LINE_AA)
            x, y, z = obj.position
            cv2.putText(out, f"{obj.name} {obj.score:.2f} ({x:+.2f},{y:+.2f})", (p1[0], p1[1] - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 90, 90), 1, cv2.LINE_AA)
        for d in perc.summary.detections:  # RT-DETR safety-relevant classes only
            if perc.summary.safety_stop:
                b = d.box
                cv2.rectangle(out, (int(b.x1), int(b.y1)), (int(b.x2), int(b.y2)), (255, 0, 0), 2)
    if flags.ocr:
        for lab in perc.summary.ocr:
            b = lab.box
            cv2.rectangle(out, (int(b.x1), int(b.y1)), (int(b.x2), int(b.y2)), (255, 215, 0), 1, cv2.LINE_AA)
    if flags.hud and hud:
        cv2.rectangle(out, (0, 0), (out.shape[1], 20), (20, 20, 20), -1)
        cv2.putText(out, hud, (6, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (230, 230, 230), 1, cv2.LINE_AA)
    if perc.summary.safety_stop:
        cv2.putText(out, "SAFETY HOLD", (10, out.shape[0] - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 0), 2)
    return out
