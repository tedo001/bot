"""Qt-free core: wires simulator -> perception -> VLA brain -> controller.

Kept independent of PyQt so it can be unit-tested headless and reused by a ROS
node or a CLI benchmark. ``workers.py`` runs it inside QThreads.

Data flow per control tick (control thread)::

    sim.render() --FramePacket--> frame_slot ---> PerceptionWorker (own thread)
                                                     |
    perception_slot <--------PerceptionOutput--------+
         | (peek, non-blocking: newest available, never waits)
    brain.step(make_obs) --ActionCommand--> controller.apply() --> sim.apply_delta()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from .brain.policies import Observation
from .brain.vla_brain import VLABrain
from .config import AppConfig
from .control.robot_controller import RobotController
from .frame_bus import FramePacket, LatestSlot
from .perception.pipeline import PerceptionOutput, PerceptionPipeline
from .schemas import ActionCommand, InstructionPayload, RobotState
from .sim.simulator import TabletopSim

log = logging.getLogger(__name__)


def make_sim(cfg: AppConfig):
    """Pick the simulator backend. Both expose camera / reset / apply_delta / render / state."""
    if cfg.sim_backend in ("auto", "pybullet"):
        try:
            from .sim.pybullet_sim import PyBulletSim

            sim = PyBulletSim(cfg.frame_width, cfg.frame_height, model=cfg.robot_model, detail=cfg.sim_mesh_detail,
                              control_hz=cfg.control_hz, async_render=cfg.sim_async_render, use_egl=cfg.sim_use_egl)
            log.info("simulator: PyBullet + Yaskawa Motoman %s (%s meshes, %s render)", cfg.robot_model.upper(),
                     cfg.sim_mesh_detail, "async" if cfg.sim_async_render else "sync")
            return sim
        except Exception as exc:  # noqa: BLE001 - missing pybullet/meshes -> fall back
            if cfg.sim_backend == "pybullet":
                raise
            log.warning("PyBullet simulator unavailable (%s); using the kinematic simulator", exc)
    log.info("simulator: kinematic (numpy/OpenCV)")
    return TabletopSim(cfg.frame_width, cfg.frame_height)


@dataclass(slots=True)
class TickResult:
    packet: FramePacket
    robot: RobotState
    command: ActionCommand
    perception: PerceptionOutput | None
    done: bool


class Engine:
    def __init__(self, cfg: AppConfig, brain: VLABrain | None = None) -> None:
        self.cfg = cfg
        self.sim = make_sim(cfg)
        self.perception = PerceptionPipeline(cfg, self.sim.camera)
        self.brain = brain or VLABrain(cfg)
        self.controller = RobotController(cfg, self.sim)
        self.frame_slot: LatestSlot[FramePacket] = LatestSlot()
        self.perception_slot: LatestSlot[PerceptionOutput] = LatestSlot()
        self.loaded = False
        self._last_frame_id = -1

    def load(self) -> None:
        """Load every model (slow). Called from a worker thread."""
        self.perception.load()
        self.brain.load()
        self.loaded = True

    def start_episode(self, payload: InstructionPayload) -> None:
        self.controller.reset()
        self.brain.set_instruction(payload)

    def stop_episode(self) -> None:
        self.brain.clear_instruction()

    def reset_scene(self) -> None:
        self.brain.clear_instruction()
        self.sim.reset()
        self.perception.invalidate()
        self.controller.reset()

    def _make_obs_factory(self, pkt: FramePacket, perc: PerceptionOutput | None):
        def make_obs(text: str) -> Observation:
            s = self.sim.state()
            return Observation(rgb=pkt.rgb, instruction=text, ee=s["ee"], rpy=s["rpy"], gripper=s["gripper"],
                               holding=s["holding"], scene=perc.index if perc else None)
        return make_obs

    def tick(self, sync_perception: bool = False) -> TickResult:
        pkt = self.sim.render()
        if pkt.frame_id != self._last_frame_id:  # async renderers may hand back the same frame twice
            self._last_frame_id = pkt.frame_id
            self.frame_slot.publish(pkt)
        if sync_perception:  # tests / benchmarks: deterministic, single-threaded
            self.perception_slot.publish(self.perception.process(pkt))
        _, perc = self.perception_slot.peek()

        self.controller.safety_hold = bool(perc and perc.summary.safety_stop)
        cmd = self.brain.step(self._make_obs_factory(pkt, perc)) if perc is not None else None
        robot, applied = self.controller.apply(cmd)
        done = self.brain.instruction is not None and self.brain.done
        return TickResult(pkt, robot, applied, perc, done)

    def object_positions(self) -> dict[str, np.ndarray]:
        return self.sim.state()["objects"]

    def shutdown(self) -> None:
        self.frame_slot.close()
        self.perception_slot.close()
        self.brain.shutdown()
        close = getattr(self.sim, "close", None)
        if close is not None:
            close()
