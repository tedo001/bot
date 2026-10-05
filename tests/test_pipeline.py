import time

import numpy as np
import pytest

from vla_dashboard.brain.policies import Observation
from vla_dashboard.brain.vla_brain import ChunkScheduler
from vla_dashboard.config import AppConfig
from vla_dashboard.engine import Engine
from vla_dashboard.frame_bus import LatestSlot
from vla_dashboard.perception.skeleton import morphological_skeleton
from vla_dashboard.schemas import InstructionPayload


def _engine():
    e = Engine(AppConfig(perception_mode="mock", brain_backend="mock"))
    e.load()
    return e


def _run(e, text, max_steps=400):
    e.start_episode(InstructionPayload(text=text))
    for _ in range(max_steps):
        r = e.tick(sync_perception=True)
        if r.done:
            return r
    raise AssertionError("episode did not finish")


def test_perception_localises_objects_in_3d():
    e = _engine()
    out = e.perception.process(e.sim.render())
    truth = e.object_positions()
    for name in ("cube", "cylinder", "sphere"):
        obj = out.index.lookup(name)
        assert obj is not None
        assert np.linalg.norm(np.array(obj.position[:2]) - truth[name][:2]) < 0.01


def test_synonym_retrieval():
    e = _engine()
    idx = e.perception.process(e.sim.render()).index
    assert [o.name for o in idx.resolve("put the red block on the ball")] == ["cube", "sphere"]


@pytest.mark.parametrize("text,check", [
    ("pick up the red cube", lambda e, r: r.robot.holding == "cube"),
    ("put the red cube on the blue cylinder",
     lambda e, r: np.linalg.norm(e.object_positions()["cube"][:2] - e.object_positions()["cylinder"][:2]) < 0.02
     and e.object_positions()["cube"][2] > 0.07),
    ("place the green ball next to the cube",
     lambda e, r: np.linalg.norm(e.object_positions()["sphere"][:2] - e.object_positions()["cube"][:2]) < 0.1),
])
def test_episodes_succeed(text, check):
    e = _engine()
    r = _run(e, text)
    assert check(e, r), e.object_positions()
    assert e.brain.policy.failed is None


def test_unknown_object_fails_cleanly():
    e = _engine()
    _run(e, "pick up the purple banana")
    assert e.brain.policy.failed


def test_estop_holds_position():
    e = _engine()
    e.controller.estop = True
    e.start_episode(InstructionPayload(text="pick up the cube"))
    before = e.sim.state()["ee"].copy()
    for _ in range(20):
        e.tick(sync_perception=True)
    assert np.allclose(before, e.sim.state()["ee"])


def test_tick_latency_budget():
    e = _engine()
    e.start_episode(InstructionPayload(text="pick up the cube"))
    t = time.perf_counter()
    for _ in range(50):
        e.tick(sync_perception=True)
    assert (time.perf_counter() - t) / 50 < 0.02  # well inside one 20 Hz period


def test_latest_slot_drops_stale():
    s = LatestSlot()
    for i in range(10):
        s.publish(i)
    seq, item = s.wait_newer(0, timeout=0.1)
    assert (seq, item) == (10, 9)


class _SlowChunkPolicy:
    source, failed, phase = "test", None, "t"
    done = False

    def __init__(self):
        self.calls = 0

    def load(self): ...
    def reset(self): ...

    def infer(self, obs):
        self.calls += 1
        time.sleep(0.05)
        return np.tile(np.arange(8, dtype=float)[:, None], (1, 7)) + 100 * self.calls


def test_prefetch_and_delay_compensation():
    pol = _SlowChunkPolicy()
    sch = ChunkScheduler(pol, prefetch_ratio=0.5, timeout_s=1.0)
    obs = lambda: Observation(np.zeros((4, 4, 3), np.uint8), "x", np.zeros(3), np.zeros(3), 1.0, None, None)  # noqa: E731
    first = [sch.next_action(obs)[0] for _ in range(8)]
    assert first == [100 + i for i in range(8)]
    # Prefetch was issued at step 4; 4 actions executed since -> first 4 of chunk 2 are skipped.
    nxt = sch.next_action(obs)[0]
    assert pol.calls == 2 and nxt == 204


def test_skeleton_is_thin():
    m = np.zeros((40, 40), bool)
    m[10:30, 5:35] = True
    sk = morphological_skeleton(m)
    assert 0 < (sk > 0).sum() < m.sum() * 0.3
