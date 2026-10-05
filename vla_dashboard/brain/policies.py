"""Policy backends. All return an action *chunk*: an (H, 7) array of
(dx, dy, dz, droll, dpitch, dyaw, gripper_delta) in the dashboard's convention.

* ``LearnedPolicy`` (vla_dashboard/learning): trained transformer, the default.
* ``OKRobotScriptedPolicy``: rule-based OK-Robot-style planner. Used as the *teacher*
  that generates training demonstrations, and selectable as the "mock" backend.
* ``OpenVLARestPolicy``: talks to ``openvla/vla-scripts/deploy.py`` (POST /act).
* ``OpenPIWebsocketPolicy``: talks to ``openpi/scripts/serve_policy.py`` through
  ``openpi_client`` (LIBERO observation format, action chunks of 10+ steps).

Each remote backend keeps a persistent connection (HTTP keep-alive / websocket)
so per-call latency is just inference time plus one round trip.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np

from ..config import AppConfig
from ..perception.pipeline import SceneIndex
from ..sim.simulator import GRIPPER_RATE

log = logging.getLogger(__name__)


@dataclass(slots=True)
class Observation:
    rgb: np.ndarray  # (H, W, 3) uint8, shared read-only
    instruction: str
    ee: np.ndarray  # (3,)
    rpy: np.ndarray  # (3,)
    gripper: float  # opening, 1 = open
    holding: str | None
    scene: SceneIndex | None


class Policy(Protocol):
    source: str

    def load(self) -> None: ...
    def reset(self) -> None: ...
    def infer(self, obs: Observation) -> np.ndarray: ...
    @property
    def done(self) -> bool: ...
    @property
    def phase(self) -> str: ...
    @property
    def failed(self) -> str | None: ...


def _gripper_delta(target_opening: float, current: float) -> float:
    """Convert an absolute gripper target into the delta convention used by ActionCommand."""
    return float(np.clip((target_opening - current) / GRIPPER_RATE, -1.0, 1.0))


def _resize(rgb: np.ndarray, size: int = 224) -> np.ndarray:
    try:
        from openpi_client import image_tools  # type: ignore

        return image_tools.convert_to_uint8(image_tools.resize_with_pad(rgb, size, size))
    except ImportError:
        return cv2.resize(rgb, (size, size), interpolation=cv2.INTER_AREA)


# ======================================================================================
# OK-Robot style scripted policy
# ======================================================================================
_PLACE = re.compile(r"\b(on|onto|on top of|next to|beside|near|into|in)\b")
_PICK = re.compile(r"\b(pick|grab|grasp|lift|take|get|put|place|stack|move|bring)\b")
_HOME = re.compile(r"\b(home|reset|retract)\b")


HOME_POS = np.array([0.10, 0.60, 0.25])
TASKS = ("pick", "stack", "next_to", "home")


def plan_waypoints(task: str, src: np.ndarray | None = None, dst: np.ndarray | None = None,
                   hover_z: float = 0.14, lift_z: float = 0.16) -> list[tuple[str, np.ndarray | None, float]]:
    """Waypoints (phase name, target xyz or None for gripper-only, gripper opening) for a task."""
    if task == "home":
        return [("home", HOME_POS.copy(), 1.0)]
    src = np.asarray(src, dtype=np.float64)
    plan = [
        ("approach", np.array([src[0], src[1], hover_z]), 1.0),
        ("descend", src.copy(), 1.0),
        ("grasp", None, 0.0),
        ("lift", np.array([src[0], src[1], lift_z]), 0.0),
    ]
    if task in ("stack", "next_to"):
        dst = np.asarray(dst, dtype=np.float64)
        if task == "next_to":  # offset sideways toward the side the object came from
            side = 1.0 if src[0] > dst[0] else -1.0
            dst = dst + np.array([0.07 * side, 0.0, 0.0])
        place_z = (dst[2] + 0.055) if task == "stack" else src[2]
        plan += [
            ("transport", np.array([dst[0], dst[1], lift_z]), 0.0),
            ("lower", np.array([dst[0], dst[1], place_z]), 0.0),
            ("release", None, 1.0),
            ("retreat", np.array([dst[0], dst[1], lift_z]), 1.0),
        ]
    return plan


class OKRobotScriptedPolicy:
    """Closed-loop waypoint policy: approach -> descend -> grasp -> lift -> transport ->
    lower -> release -> retreat. Targets come from the perception scene index, so a
    wrong detection or failed grounding shows up as a wrong motion, exactly like a
    learned VLA would fail."""

    source = "mock"
    HOVER_Z, LIFT_Z, TOL = 0.14, 0.16, 0.006

    def __init__(self, cfg: AppConfig) -> None:
        self.max_step = cfg.max_translation_step
        self.horizon = cfg.action_horizon
        self.reset()

    def load(self) -> None:
        pass

    def reset(self) -> None:
        self._plan: list[tuple[str, np.ndarray | None, float]] | None = None
        self._i = 0
        self._hold_ticks = 0
        self._phase = "idle"
        self._failed: str | None = None

    @property
    def done(self) -> bool:
        return self._plan is not None and self._i >= len(self._plan)

    @property
    def phase(self) -> str:
        return self._failed or self._phase

    @property
    def failed(self) -> str | None:
        return self._failed

    def set_task(self, task: str, src: np.ndarray | None = None, dst: np.ndarray | None = None) -> None:
        """Teacher mode (used to generate training demonstrations): give the task and the
        object positions directly instead of parsing the instruction."""
        self.reset()
        self._plan = plan_waypoints(task, src, dst, self.HOVER_Z, self.LIFT_Z)

    def _make_plan(self, obs: Observation) -> list | None:
        text = obs.instruction.lower()
        if _HOME.search(text) and not _PICK.search(text):
            return plan_waypoints("home")
        if obs.scene is None:
            return None
        objs = obs.scene.resolve(text)
        if not objs:
            self._failed = "no object in instruction matched the scene"
            return []
        src = np.asarray(objs[0].position)
        if len(objs) > 1 and _PLACE.search(text):
            task = "stack" if re.search(r"\b(on|onto|on top of)\b", text) else "next_to"
            return plan_waypoints(task, src, np.asarray(objs[1].position), self.HOVER_Z, self.LIFT_Z)
        return plan_waypoints("pick", src, None, self.HOVER_Z, self.LIFT_Z)

    def infer(self, obs: Observation) -> np.ndarray:
        if self._plan is None:
            self._plan = self._make_plan(obs)
            if self._plan is None:
                return np.zeros((1, 7))
        ee, g = obs.ee.astype(np.float64).copy(), float(obs.gripper)
        holding = obs.holding
        chunk = np.zeros((self.horizon, 7))
        for k in range(self.horizon):  # roll the plan forward for H steps (open-loop within a chunk)
            if self._i >= len(self._plan):
                return chunk[: max(k, 1)]
            name, wp, grip = self._plan[self._i]
            self._phase = name
            if wp is None:  # gripper-only phase: wait until the gripper settles
                chunk[k, 6] = _gripper_delta(grip, g)
                g = float(np.clip(g + GRIPPER_RATE * chunk[k, 6], 0.0, 1.0))
                if holding and grip == 0.0:
                    g = max(g, 0.3)
                self._hold_ticks += 1
                if self._hold_ticks >= 4:
                    self._hold_ticks = 0
                    self._i += 1
                continue
            err = wp - ee
            step = np.clip(err, -self.max_step, self.max_step)
            chunk[k, :3] = step
            chunk[k, 5] = -obs.rpy[2] * 0.3 if k == 0 else 0.0  # keep fingers aligned with world x
            chunk[k, 6] = _gripper_delta(grip, g)
            ee = ee + step
            g = float(np.clip(g + GRIPPER_RATE * chunk[k, 6], 0.0, 1.0))
            if np.linalg.norm(wp - ee) < self.TOL:
                self._i += 1
        return chunk


# ======================================================================================
# OpenVLA (REST) - openvla/vla-scripts/deploy.py
# ======================================================================================
class OpenVLARestPolicy:
    """OpenVLA predicts one 7-DoF action per call: EE delta + absolute gripper in [0, 1].
    Note: OpenVLA's action frame is the training robot's (e.g. WidowX for BridgeData);
    re-map axes here if your simulator/robot frame differs."""

    source = "openvla"

    def __init__(self, cfg: AppConfig) -> None:
        self.url, self.unnorm_key, self.timeout = cfg.openvla_url, cfg.openvla_unnorm_key, cfg.inference_timeout_s
        self._session = None

    def load(self) -> None:
        import json_numpy  # type: ignore  # the server decodes arrays with json_numpy
        import requests

        json_numpy.patch()
        self._session = requests.Session()  # keep-alive: no TCP handshake per step
        log.info("OpenVLA client -> %s", self.url)

    def reset(self) -> None:
        pass

    done = False
    failed = None
    phase = "openvla"

    def infer(self, obs: Observation) -> np.ndarray:
        payload = {"image": _resize(obs.rgb), "instruction": obs.instruction, "unnorm_key": self.unnorm_key}
        r = self._session.post(self.url, json=payload, timeout=self.timeout)
        r.raise_for_status()
        a = np.asarray(r.json(), dtype=np.float64).reshape(-1)
        out = a[:7].copy()
        out[6] = _gripper_delta(float(np.clip(a[6], 0.0, 1.0)), obs.gripper)
        return out[None]


# ======================================================================================
# openpi π₀ / π₀-FAST (websocket) - openpi/scripts/serve_policy.py
# ======================================================================================
class OpenPIWebsocketPolicy:
    """Uses the LIBERO observation/action convention: actions in [-1, 1] scaled by the
    OSC controller limits (0.05 m, 0.5 rad), gripper +1 = close. Returns the full
    chunk; the ChunkScheduler executes it step by step without re-querying."""

    source = "openpi"
    POS_SCALE, ROT_SCALE = 0.05, 0.5

    def __init__(self, cfg: AppConfig) -> None:
        self.host, self.port = cfg.openpi_host, cfg.openpi_port
        self._client = None

    def load(self) -> None:
        from openpi_client import websocket_client_policy  # type: ignore

        self._client = websocket_client_policy.WebsocketClientPolicy(host=self.host, port=self.port)
        log.info("openpi server metadata: %s", self._client.get_server_metadata())

    def reset(self) -> None:
        if self._client is not None:
            self._client.reset()

    done = False
    failed = None
    phase = "openpi"

    def infer(self, obs: Observation) -> np.ndarray:
        img = _resize(obs.rgb)
        state = np.concatenate([obs.ee, obs.rpy, [obs.gripper * 0.04, -obs.gripper * 0.04]]).astype(np.float32)
        result = self._client.infer({
            "observation/image": img,
            "observation/wrist_image": img,  # no wrist camera in the sim; reuse the base view
            "observation/state": state,
            "prompt": obs.instruction,
        })
        a = np.asarray(result["actions"], dtype=np.float64)[:, :7]
        out = np.empty_like(a)
        out[:, :3] = a[:, :3] * self.POS_SCALE
        out[:, 3:6] = a[:, 3:6] * self.ROT_SCALE
        g = obs.gripper
        for k in range(a.shape[0]):  # +1 close / -1 open  ->  opening target -> delta
            out[k, 6] = _gripper_delta((1.0 - np.clip(a[k, 6], -1, 1)) / 2.0, g)
            g = float(np.clip(g + GRIPPER_RATE * out[k, 6], 0.0, 1.0))
        return out


def make_policy(cfg: AppConfig) -> Policy:
    if cfg.brain_backend == "learned":
        from ..learning.policy import LearnedPolicy

        return LearnedPolicy(cfg)
    return {"mock": OKRobotScriptedPolicy, "openvla": OpenVLARestPolicy, "openpi": OpenPIWebsocketPolicy}[
        cfg.brain_backend
    ](cfg)
