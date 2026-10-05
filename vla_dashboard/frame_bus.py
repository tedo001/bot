"""Low-latency hand-off between pipeline stages.

Why not ``queue.Queue``? A queue buffers frames, so when a consumer (e.g. a detector)
is slower than the producer (the simulator) latency grows without bound: the
detector keeps processing frames that are seconds old. ``LatestSlot`` keeps only the
newest item ("latest wins"). A slow consumer skips stale frames and always works on
the freshest one, so end-to-end latency is bounded by one producer period plus one
consumer run.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Generic, TypeVar

import numpy as np

T = TypeVar("T")


class LatestSlot(Generic[T]):
    """Single-value mailbox with a sequence number. Thread-safe, never blocks the producer."""

    __slots__ = ("_cond", "_item", "_seq", "_closed")

    def __init__(self) -> None:
        self._cond = threading.Condition(threading.Lock())
        self._item: T | None = None
        self._seq = 0
        self._closed = False

    def publish(self, item: T) -> int:
        with self._cond:
            self._item = item
            self._seq += 1
            self._cond.notify_all()
            return self._seq

    def peek(self) -> tuple[int, T | None]:
        """Non-blocking read of the newest item (used by the control loop)."""
        with self._cond:
            return self._seq, self._item

    def wait_newer(self, last_seq: int, timeout: float | None = None) -> tuple[int, T | None]:
        """Block until an item newer than ``last_seq`` exists (used by worker threads)."""
        with self._cond:
            self._cond.wait_for(lambda: self._seq > last_seq or self._closed, timeout=timeout)
            return self._seq, self._item

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    def reopen(self) -> None:
        with self._cond:
            self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed


@dataclass(slots=True)
class FramePacket:
    """One rendered simulator frame plus the metadata downstream stages need.

    ``rgb`` is an (H, W, 3) uint8, C-contiguous array. It is treated as immutable once
    published: every consumer reads the same buffer, nobody copies it, nobody writes it.
    ``instance_ids`` (H, W) uint8 is simulator ground truth, used only by mock models.
    """

    frame_id: int
    timestamp: float
    rgb: np.ndarray
    instance_ids: np.ndarray | None = None
    gt_objects: dict[int, str] = field(default_factory=dict)  # instance id -> name
    gt_labels: list[tuple[str, tuple[float, float, float, float]]] = field(default_factory=list)
    robot_skeleton_2d: np.ndarray | None = None  # (J, 2) projected joint pixels
