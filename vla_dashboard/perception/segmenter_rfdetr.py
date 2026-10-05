"""RF-DETR instance segmentation (Roboflow ``rfdetr`` package, Apache-2.0).

Produces per-object masks, which drive the mask overlay and the skeleton view.
It is the heaviest per-frame model, so it runs every ``seg_stride`` frames and the
last masks are reused in between (objects move at most a few pixels per tick).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from ..frame_bus import FramePacket
from ..schemas import BBox, Detection
from .detector_rtdetr import gt_boxes

log = logging.getLogger(__name__)

# Class names differ between rfdetr releases; the first one present is used.
_SEG_CLASSES = ("RFDETRSegMedium", "RFDETRSegSmall", "RFDETRSegNano", "RFDETRSegPreview")


@dataclass(slots=True)
class SegmentationResult:
    detections: list[Detection]
    masks: np.ndarray  # (N, H, W) bool, aligned with detections


class RFDetrSegmenter:
    def __init__(self, threshold: float = 0.5, mode: str = "auto") -> None:
        self.threshold, self.mode = threshold, mode
        self.backend = "mock"
        self._model = None
        self._names: dict[int, str] = {}

    def load(self) -> None:
        if self.mode == "mock":
            return
        try:
            import rfdetr  # type: ignore

            cls = next(getattr(rfdetr, n) for n in _SEG_CLASSES if hasattr(rfdetr, n))
            self._model = cls()
            try:
                self._model.optimize_for_inference()  # TorchScript/fused graph; big latency win
            except Exception as exc:  # noqa: BLE001
                log.info("RF-DETR optimize_for_inference skipped: %s", exc)
            try:
                from rfdetr.util.coco_classes import COCO_CLASSES  # type: ignore

                self._names = dict(COCO_CLASSES)
            except Exception:  # noqa: BLE001
                self._names = {}
            self._model.predict(np.zeros((480, 640, 3), np.uint8), threshold=self.threshold)  # warm-up
            self.backend = f"rfdetr:{cls.__name__}"
            log.info("RF-DETR segmentation loaded (%s)", cls.__name__)
        except Exception as exc:  # noqa: BLE001
            if self.mode == "real":
                raise
            self._model = None
            log.warning("RF-DETR unavailable (%s); using simulator ground-truth masks", exc)

    def segment(self, pkt: FramePacket) -> SegmentationResult:
        if self._model is None:
            return self._mock(pkt)
        sv = self._model.predict(pkt.rgb, threshold=self.threshold)  # supervision.Detections
        dets, masks = [], []
        mask_arr = sv.mask if sv.mask is not None else None
        for i, (box, score, cid) in enumerate(zip(sv.xyxy, sv.confidence, sv.class_id)):
            x1, y1, x2, y2 = map(float, box)
            if x2 <= x1 or y2 <= y1:
                continue
            dets.append(Detection(label=self._names.get(int(cid), str(int(cid))), score=float(score),
                                  box=BBox(x1=x1, y1=y1, x2=x2, y2=y2), source="rfdetr",
                                  has_mask=mask_arr is not None))
            if mask_arr is not None:
                masks.append(mask_arr[i])
        h, w = pkt.rgb.shape[:2]
        return SegmentationResult(dets, np.stack(masks) if masks else np.zeros((0, h, w), bool))

    @staticmethod
    def _mock(pkt: FramePacket) -> SegmentationResult:
        ids = pkt.instance_ids
        name_to_id = {v: k for k, v in pkt.gt_objects.items()}
        dets, masks = [], []
        for name, box in gt_boxes(pkt):
            dets.append(Detection(label=name, score=0.97, box=box, source="mock", has_mask=True))
            masks.append(ids == name_to_id[name])
        h, w = pkt.rgb.shape[:2]
        return SegmentationResult(dets, np.stack(masks) if masks else np.zeros((0, h, w), bool))
