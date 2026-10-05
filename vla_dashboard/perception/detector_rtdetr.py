"""RT-DETR supportive detection layer (HuggingFace transformers, Apache-2.0 weights).

Deliberately NOT ultralytics (AGPL-3.0). RT-DETR runs on every ``det_stride``-th
frame and plays two supporting roles:

1. Safety: any class in ``safety_labels`` (default "person") inside the frame puts
   the controller into a safety hold.
2. Fallback localisation: boxes keep the scene index fresh on frames where the
   heavier RF-DETR segmentation is skipped.

Latency tricks: fp16 on CUDA, ``torch.inference_mode``, one warm-up pass at load
time so the first real frame doesn't pay for CUDA kernel compilation.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from ..frame_bus import FramePacket
from ..schemas import BBox, Detection

log = logging.getLogger(__name__)


def gt_boxes(pkt: FramePacket) -> list[tuple[str, BBox]]:
    """Tight boxes from the simulator's instance mask (shared by the mock models)."""
    out = []
    ids = pkt.instance_ids
    if ids is None:
        return out
    for iid, name in pkt.gt_objects.items():
        x, y, w, h = cv2.boundingRect((ids == iid).view(np.uint8))  # SIMD, ~10x faster than np.nonzero
        if w < 2 or h < 2:
            continue  # fully occluded
        out.append((name, BBox(x1=x, y1=y, x2=x + w, y2=y + h)))
    return out


class RTDetrDetector:
    def __init__(self, checkpoint: str, threshold: float = 0.5, mode: str = "auto") -> None:
        self.checkpoint, self.threshold, self.mode = checkpoint, threshold, mode
        self.backend = "mock"
        self._model = self._proc = self._torch = self._device = None

    def load(self) -> None:
        if self.mode == "mock":
            return
        try:
            import torch
            from transformers import AutoImageProcessor, AutoModelForObjectDetection

            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if self._device == "cuda" else torch.float32
            self._proc = AutoImageProcessor.from_pretrained(self.checkpoint)
            self._model = AutoModelForObjectDetection.from_pretrained(self.checkpoint, torch_dtype=dtype)
            self._model.to(self._device).eval()
            self._torch = torch
            self.detect_rgb(np.zeros((480, 640, 3), np.uint8))  # warm-up
            self.backend = "rtdetr"
            log.info("RT-DETR %s loaded on %s", self.checkpoint, self._device)
        except Exception as exc:  # noqa: BLE001
            if self.mode == "real":
                raise
            self._model = None
            log.warning("RT-DETR unavailable (%s); using mock detector", exc)

    def detect(self, pkt: FramePacket) -> list[Detection]:
        if self._model is None:
            return [Detection(label=n, score=0.95, box=b, source="mock") for n, b in gt_boxes(pkt)]
        return self.detect_rgb(pkt.rgb)

    def detect_rgb(self, rgb: np.ndarray) -> list[Detection]:
        torch = self._torch
        h, w = rgb.shape[:2]
        inputs = self._proc(images=rgb, return_tensors="pt").to(self._device)
        inputs["pixel_values"] = inputs["pixel_values"].to(self._model.dtype)
        with torch.inference_mode():
            outputs = self._model(**inputs)
        res = self._proc.post_process_object_detection(
            outputs, target_sizes=torch.tensor([(h, w)]), threshold=self.threshold
        )[0]
        id2label = self._model.config.id2label
        dets = []
        for score, label, box in zip(res["scores"].tolist(), res["labels"].tolist(), res["boxes"].tolist()):
            x1, y1, x2, y2 = box
            if x2 > x1 and y2 > y1:
                dets.append(Detection(label=id2label[int(label)], score=float(score),
                                      box=BBox(x1=x1, y1=y1, x2=x2, y2=y2), source="rtdetr"))
        return dets
