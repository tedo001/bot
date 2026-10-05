"""RobotController: the only component allowed to move the robot.

Responsibilities, in order, for every command:
  1. Safety hold (e-stop button or RT-DETR safety label) -> zero motion.
  2. Watchdog: no fresh command within ``watchdog_s`` -> zero motion.
  3. Per-tick rate limits (tighter than the schema's absolute limits).
  4. Forward to the backend (simulator here; a home-robot / hardware adapter on a
     real arm) and return a validated ``RobotState``.
"""

from __future__ import annotations

import logging
import time

import numpy as np

from ..config import AppConfig
from ..schemas import ActionCommand, RobotState

log = logging.getLogger(__name__)


class RobotController:
    def __init__(self, cfg: AppConfig, backend) -> None:
        self.cfg = cfg
        self.backend = backend  # needs apply_delta(np.ndarray[7]) and state() -> dict
        self.estop = False
        self.safety_hold = False
        self._last_cmd_time = time.monotonic()
        self.step_count = 0
        self._lim = np.array([cfg.max_translation_step] * 3 + [cfg.max_rotation_step] * 3 + [1.0])

    def reset(self) -> None:
        self.step_count = 0
        self._last_cmd_time = time.monotonic()
        self.safety_hold = False  # estop is operator-owned: only the E-STOP toggle releases it

    def apply(self, cmd: ActionCommand | None) -> tuple[RobotState, ActionCommand]:
        now = time.monotonic()
        if cmd is not None:
            self._last_cmd_time = now
        if self.estop or self.safety_hold:
            cmd = ActionCommand.hold()
        elif cmd is None:
            if now - self._last_cmd_time > self.cfg.watchdog_s:
                log.debug("watchdog: no command for %.2fs", now - self._last_cmd_time)
            cmd = ActionCommand.hold()
        delta = np.clip(cmd.to_array(), -self._lim, self._lim)
        self.backend.apply_delta(delta)
        self.step_count += 1
        return self.state(), cmd

    def state(self) -> RobotState:
        s = self.backend.state()
        return RobotState(
            ee_position=tuple(map(float, s["ee"])),
            ee_rpy=tuple(map(float, s["rpy"])),
            gripper_opening=float(s["gripper"]),
            holding=s["holding"],
            step=self.step_count,
        )


def to_home_robot_action(cmd: ActionCommand, state: RobotState):
    """Adapter for facebookresearch/home-robot (OK-Robot's stack): absolute EE target as
    ``ContinuousEndEffectorAction`` (pos 3 + quaternion 4 + gripper 1)."""
    from home_robot.core.interfaces import ContinuousEndEffectorAction  # type: ignore
    from scipy.spatial.transform import Rotation  # type: ignore

    pos = np.asarray(state.ee_position) + cmd.to_array()[:3]
    rpy = np.asarray(state.ee_rpy) + cmd.to_array()[3:6]
    quat = Rotation.from_euler("xyz", rpy).as_quat()
    g = np.clip(state.gripper_opening + 0.25 * cmd.gripper, 0.0, 1.0)
    return ContinuousEndEffectorAction(pos[None], quat[None], np.array([[g]]))
