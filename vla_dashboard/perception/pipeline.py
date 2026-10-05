"""Perception pipeline: stride scheduling + grounding + O(1) scene index.

Per frame, stages run on a schedule instead of all at once:

    stage        cadence                    why
    RT-DETR      every det_stride frames    cheap, safety-critical
    RF-DETR seg  every seg_stride frames    heaviest; masks reused in between
    PaddleOCR    every ocr_interval_s       labels are static; cached

The fused result is a ``SceneIndex``: a dict from grounded object name (and its
synonyms) to a ``SceneObject`` with a 3D position. The VLA brain resolves
"pick up the red block" to a target with one dict lookup instead of scanning
detections every tick. That is the fast-retrieval path.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np

from ..config import AppConfig
from ..frame_bus import FramePacket
from ..schemas import Detection, OCRLabel, PerceptionSummary, SceneObject
from .detector_rtdetr import RTDetrDetector
from .ocr import WorkspaceOCR
from .segmenter_rfdetr import RFDetrSegmenter, SegmentationResult
from .skeleton import object_skeletons

log = logging.getLogger(__name__)

# Words a user might say -> canonical object name. Extend for new objects.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "cube": ("cube", "block", "box", "red"),
    "cylinder": ("cylinder", "can", "cup", "tube", "blue"),
    "sphere": ("sphere", "ball", "orb", "green"),
}
OBJECT_CENTER_Z = 0.025  # assumed object centre height when lifting 2D boxes to 3D


@dataclass(slots=True)
class SceneIndex:
    objects: dict[str, SceneObject] = field(default_factory=dict)
    alias: dict[str, str] = field(default_factory=dict)  # word -> canonical name

    def lookup(self, word: str) -> SceneObject | None:
        name = self.alias.get(word.lower(), word.lower())
        return self.objects.get(name)

    def resolve(self, text: str) -> list[SceneObject]:
        """All objects mentioned in ``text``, in order of mention (O(words))."""
        seen, out = set(), []
        for w in text.lower().replace(",", " ").split():
            obj = self.lookup(w.strip(".!?"))
            if obj is not None and obj.name not in seen:
                seen.add(obj.name)
                out.append(obj)
        return out


@dataclass(slots=True)
class PerceptionOutput:
    summary: PerceptionSummary
    index: SceneIndex
    masks: np.ndarray  # (N, H, W) bool
    mask_labels: list[str]
    skeleton: np.ndarray | None  # (H, W) uint8
    robot_skeleton_2d: np.ndarray | None


class PerceptionPipeline:
    def __init__(self, cfg: AppConfig, camera) -> None:
        self.cfg = cfg
        self.camera = camera  # needs .deproject_to_plane(u, v, z)
        self.ocr = WorkspaceOCR(cfg.perception_mode)
        self.detector = RTDetrDetector(cfg.rtdetr_checkpoint, cfg.rtdetr_threshold, cfg.perception_mode)
        self.segmenter = RFDetrSegmenter(cfg.rfdetr_threshold, cfg.perception_mode)
        self._n = 0
        self._last_dets: list[Detection] = []
        self._last_seg: SegmentationResult | None = None
        self._last_skel: np.ndarray | None = None
        self._ocr_cache: list[OCRLabel] = []
        self._ocr_time = -1e9

    def load(self) -> None:
        for name, comp in (("ocr", self.ocr), ("rtdetr", self.detector), ("rfdetr", self.segmenter)):
            t = time.perf_counter()
            comp.load()
            log.info("perception/%s ready: backend=%s (%.0f ms)", name, comp.backend,
                     (time.perf_counter() - t) * 1e3)

    def process(self, pkt: FramePacket) -> PerceptionOutput:
        stage: dict[str, float] = {}
        n = self._n
        self._n += 1

        def timed(key, fn):
            t = time.perf_counter()
            r = fn()
            stage[key] = (time.perf_counter() - t) * 1e3
            return r

        now = time.monotonic()
        if now - self._ocr_time >= self.cfg.ocr_interval_s:
            self._ocr_cache = timed("ocr", lambda: self.ocr.scan(pkt))
            self._ocr_time = now
        if n % self.cfg.det_stride == 0:
            self._last_dets = timed("rtdetr", lambda: self.detector.detect(pkt))
        if self._last_seg is None or n % self.cfg.seg_stride == 0:
            self._last_seg = timed("rfdetr", lambda: self.segmenter.segment(pkt))
            self._last_skel = timed("skeleton", lambda: object_skeletons(self._last_seg.detections,
                                                                          self._last_seg.masks))

        t = time.perf_counter()
        index = self._build_index(self._last_seg.detections or self._last_dets, self._ocr_cache)
        stage["ground"] = (time.perf_counter() - t) * 1e3

        safety = any(d.label in self.cfg.safety_labels and d.score >= self.cfg.rtdetr_threshold
                     for d in self._last_dets)
        summary = PerceptionSummary(
            frame_id=pkt.frame_id,
            objects=tuple(index.objects.values()),
            detections=tuple(self._last_dets),
            ocr=tuple(self._ocr_cache),
            safety_stop=safety,
            stage_ms=stage,
        )
        return PerceptionOutput(summary, index, self._last_seg.masks,
                                [d.label for d in self._last_seg.detections], self._last_skel,
                                pkt.robot_skeleton_2d)

    def _build_index(self, dets: list[Detection], ocr: list[OCRLabel]) -> SceneIndex:
        # Ground: each OCR label names the detection sitting just above it (labels are
        # printed in front of objects, i.e. lower in the image).
        names: dict[int, str] = {}
        for lab in ocr:
            lu, lv = lab.box.center
            best, best_d = None, 90.0
            for i, d in enumerate(dets):
                du, dv = d.box.center
                if dv > lv:
                    continue
                dist = float(np.hypot(du - lu, dv - lv))
                if dist < best_d:
                    best, best_d = i, dist
            if best is not None:
                names[best] = lab.text.lower()

        idx = SceneIndex()
        for i, d in enumerate(dets):
            name = names.get(i, d.label.lower())
            u, v = d.box.center
            pos = self.camera.deproject_to_plane(u, v, OBJECT_CENTER_Z)
            prev = idx.objects.get(name)
            if prev is None or d.score > prev.score:
                idx.objects[name] = SceneObject(name=name, box=d.box, position=pos, score=d.score)
        for canon, words in SYNONYMS.items():
            if canon in idx.objects:
                for w in words:
                    idx.alias.setdefault(w, canon)
        for name in idx.objects:
            idx.alias[name] = name
        return idx
