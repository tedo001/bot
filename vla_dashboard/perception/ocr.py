"""Workspace text-label scanner (PaddleOCR, Apache-2.0).

Labels printed on the table are static, so OCR is the slowest but least frequent
stage: it runs once at start-up and then every ``ocr_interval_s`` seconds. Results
are cached and grounded onto detections by the pipeline (label -> nearest object),
which turns generic detector classes into the names the instruction refers to.
"""

from __future__ import annotations

import logging

import numpy as np

from ..frame_bus import FramePacket
from ..schemas import BBox, OCRLabel

log = logging.getLogger(__name__)


class WorkspaceOCR:
    def __init__(self, mode: str = "auto") -> None:
        self.mode = mode
        self._engine = None
        self.backend = "mock"

    def load(self) -> None:
        """Heavy init; call from a worker thread, never from the GUI thread."""
        if self.mode == "mock":
            return
        try:
            from paddleocr import PaddleOCR  # type: ignore

            try:  # PaddleOCR >= 3.x
                self._engine = PaddleOCR(
                    use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False
                )
            except TypeError:  # PaddleOCR 2.x
                self._engine = PaddleOCR(use_angle_cls=False, lang="en", show_log=False)
            self.backend = "paddleocr"
            log.info("PaddleOCR loaded")
        except Exception as exc:  # noqa: BLE001 - any import/weights failure -> mock
            if self.mode == "real":
                raise
            log.warning("PaddleOCR unavailable (%s); using simulator ground-truth labels", exc)

    def scan(self, pkt: FramePacket) -> list[OCRLabel]:
        if self._engine is None:
            return [OCRLabel(text=t, score=0.99, box=BBox(x1=b[0], y1=b[1], x2=b[2], y2=b[3]))
                    for t, b in pkt.gt_labels]
        return self._run_paddle(pkt.rgb)

    def _run_paddle(self, rgb: np.ndarray) -> list[OCRLabel]:
        bgr = rgb[:, :, ::-1]  # PaddleOCR expects OpenCV BGR order
        out: list[OCRLabel] = []
        if hasattr(self._engine, "predict"):  # 3.x result objects
            for res in self._engine.predict(np.ascontiguousarray(bgr)):
                r = res.json.get("res", res) if hasattr(res, "json") else res
                for text, score, poly in zip(r["rec_texts"], r["rec_scores"], r["rec_polys"]):
                    out.append(self._mk(text, score, np.asarray(poly)))
        else:  # 2.x nested lists: [[ [poly, (text, score)], ... ]]
            for page in self._engine.ocr(bgr, cls=False) or []:
                for poly, (text, score) in page or []:
                    out.append(self._mk(text, score, np.asarray(poly)))
        return [o for o in out if o is not None]

    @staticmethod
    def _mk(text: str, score: float, poly: np.ndarray) -> OCRLabel | None:
        x1, y1 = poly.min(axis=0)
        x2, y2 = poly.max(axis=0)
        if x2 <= x1 or y2 <= y1 or not text.strip():
            return None
        return OCRLabel(text=text.strip(), score=float(score), box=BBox(x1=x1, y1=y1, x2=x2, y2=y2))
