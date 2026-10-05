"""Camera stream widget: paints numpy RGB frames with zero extra copies."""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QSizePolicy, QWidget


class FrameView(QWidget):
    """Custom-painted alternative to ``QLabel.setPixmap``.

    QLabel + QPixmap would need a QImage -> QPixmap conversion (a full copy, and only
    legal on the GUI thread) for every frame, and may trigger relayouts when the
    pixmap size changes. Here the incoming numpy array is wrapped in a QImage that
    points straight at the array's memory, and ``paintEvent`` scales it on draw.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 240)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)  # we paint every pixel; skip bg erase
        self._array: np.ndarray | None = None  # keeps the pixel buffer alive while _image references it
        self._image: QImage | None = None
        self.frames_shown = 0

    def set_frame(self, rgb: np.ndarray) -> None:
        if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError("expected (H, W, 3) uint8 RGB")
        if not rgb.flags["C_CONTIGUOUS"]:
            rgb = np.ascontiguousarray(rgb)
        h, w, _ = rgb.shape
        # Zero-copy: QImage reads directly from the numpy buffer (stride = 3 * w bytes).
        self._array = rgb
        self._image = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        self.frames_shown += 1
        self.update()  # schedules one repaint; multiple updates before paint are coalesced

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt naming)
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(24, 26, 30))
        if self._image is not None:
            iw, ih = self._image.width(), self._image.height()
            scale = min(self.width() / iw, self.height() / ih)
            w, h = iw * scale, ih * scale
            target = QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.drawImage(target, self._image)
        else:
            p.setPen(QColor(160, 160, 160))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Loading models… camera stream starts shortly")
        p.end()
