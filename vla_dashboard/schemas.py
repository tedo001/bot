"""Strict Pydantic v2 schemas for every message that crosses a component boundary.

Design rule for latency: Pydantic validates at *boundaries* (GUI -> brain, brain ->
controller, detector -> scene index). Large numpy arrays (frames, masks) never go
through Pydantic; they travel in slotted dataclasses (see ``frame_bus.FramePacket``)
so they are passed by reference, never copied or re-validated.
"""

from __future__ import annotations

import math
import re
import time
import uuid
from enum import Enum
from typing import ClassVar, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Hard physical limits of a single action. The controller additionally clamps to the
# (usually tighter) per-tick limits in AppConfig.
MAX_TRANSLATION = 0.05  # m
MAX_ROTATION = 0.5  # rad

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


# --------------------------------------------------------------------------------------
# Instruction (GUI -> brain)
# --------------------------------------------------------------------------------------
class InstructionPayload(_Frozen):
    """A validated natural-language instruction for the VLA."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=3, max_length=512)
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = Field(default_factory=time.time)

    @field_validator("text")
    @classmethod
    def _clean_text(cls, v: str) -> str:
        if _CONTROL_CHARS.search(v):
            raise ValueError("instruction contains control characters")
        v = " ".join(v.split())  # collapse internal whitespace / newlines
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("instruction must contain words")
        return v


# --------------------------------------------------------------------------------------
# Action (brain -> controller)
# --------------------------------------------------------------------------------------
class ActionCommand(_Frozen):
    """One end-effector delta command produced by the VLA.

    Translation in metres, rotation in radians (roll/pitch/yaw deltas), gripper delta
    in [-1, 1] where negative closes and positive opens.
    """

    dx: float = Field(0.0, ge=-MAX_TRANSLATION, le=MAX_TRANSLATION)
    dy: float = Field(0.0, ge=-MAX_TRANSLATION, le=MAX_TRANSLATION)
    dz: float = Field(0.0, ge=-MAX_TRANSLATION, le=MAX_TRANSLATION)
    droll: float = Field(0.0, ge=-MAX_ROTATION, le=MAX_ROTATION)
    dpitch: float = Field(0.0, ge=-MAX_ROTATION, le=MAX_ROTATION)
    dyaw: float = Field(0.0, ge=-MAX_ROTATION, le=MAX_ROTATION)
    gripper: float = Field(0.0, ge=-1.0, le=1.0)
    source: Literal["learned", "mock", "openvla", "openpi", "safety"] = "mock"
    inference_ms: float = Field(0.0, ge=0.0)

    FIELDS: ClassVar[tuple[str, ...]] = ("dx", "dy", "dz", "droll", "dpitch", "dyaw", "gripper")

    @classmethod
    def from_array(cls, arr: np.ndarray, source: str = "mock", inference_ms: float = 0.0) -> ActionCommand:
        """Build from a raw 7-vector model output, clipping to the schema limits first.

        Clipping (instead of raising) is deliberate: a model that overshoots should be
        saturated, not crash the control loop. NaN/inf still raise.
        """
        a = np.asarray(arr, dtype=np.float64).reshape(-1)
        if a.shape[0] < 7:
            raise ValueError(f"expected 7 action dims, got {a.shape[0]}")
        if not np.all(np.isfinite(a[:7])):
            raise ValueError("non-finite action")
        t = np.clip(a[:3], -MAX_TRANSLATION, MAX_TRANSLATION)
        r = np.clip(a[3:6], -MAX_ROTATION, MAX_ROTATION)
        g = float(np.clip(a[6], -1.0, 1.0))
        return cls(
            dx=t[0], dy=t[1], dz=t[2], droll=r[0], dpitch=r[1], dyaw=r[2], gripper=g,
            source=source, inference_ms=inference_ms,
        )

    @classmethod
    def hold(cls, source: Literal["learned", "mock", "openvla", "openpi", "safety"] = "safety") -> ActionCommand:
        return cls(source=source)

    def to_array(self) -> np.ndarray:
        return np.array([getattr(self, f) for f in self.FIELDS], dtype=np.float64)

    @property
    def is_hold(self) -> bool:
        return all(getattr(self, f) == 0.0 for f in self.FIELDS)


# --------------------------------------------------------------------------------------
# Perception (detectors -> scene index)
# --------------------------------------------------------------------------------------
class BBox(_Frozen):
    x1: float
    y1: float
    x2: float
    y2: float

    @model_validator(mode="after")
    def _ordered(self) -> BBox:
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("degenerate box")
        return self

    @property
    def center(self) -> tuple[float, float]:
        return (self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0

    @property
    def area(self) -> float:
        return (self.x2 - self.x1) * (self.y2 - self.y1)


class Detection(_Frozen):
    label: str
    score: float = Field(ge=0.0, le=1.0)
    box: BBox
    source: Literal["rtdetr", "rfdetr", "mock"] = "mock"
    has_mask: bool = False


class OCRLabel(_Frozen):
    text: str
    score: float = Field(ge=0.0, le=1.0)
    box: BBox


class SceneObject(_Frozen):
    """An object in the scene index: grounded name + 3D position for O(1) retrieval."""

    name: str
    box: BBox
    position: tuple[float, float, float]
    score: float = Field(ge=0.0, le=1.0)


class PerceptionSummary(_Frozen):
    frame_id: int = Field(ge=0)
    objects: tuple[SceneObject, ...] = ()
    detections: tuple[Detection, ...] = ()
    ocr: tuple[OCRLabel, ...] = ()
    safety_stop: bool = False
    stage_ms: dict[str, float] = Field(default_factory=dict)


# --------------------------------------------------------------------------------------
# Robot / system state (controller -> GUI)
# --------------------------------------------------------------------------------------
class RobotState(_Frozen):
    ee_position: tuple[float, float, float]
    ee_rpy: tuple[float, float, float]
    gripper_opening: float = Field(ge=0.0, le=1.0)  # 1 = fully open
    holding: str | None = None
    step: int = Field(0, ge=0)

    @field_validator("ee_position", "ee_rpy")
    @classmethod
    def _finite(cls, v: tuple[float, float, float]) -> tuple[float, float, float]:
        if not all(math.isfinite(x) for x in v):
            raise ValueError("non-finite pose")
        return v


class RunStatus(str, Enum):
    IDLE = "idle"
    LOADING = "loading"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    STOPPED = "stopped"
    SAFETY_HOLD = "safety_hold"
    FAILED = "failed"


class SystemState(_Frozen):
    status: RunStatus
    robot: RobotState
    last_action: ActionCommand | None = None
    phase: str = ""
    loop_hz: float = Field(0.0, ge=0.0)
    perception_hz: float = Field(0.0, ge=0.0)
    stage_ms: dict[str, float] = Field(default_factory=dict)
