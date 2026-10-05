"""Tests for the learned (imitation-trained) policy. Skipped if torch or the checkpoint is missing."""

import time

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from vla_dashboard.config import AppConfig  # noqa: E402
from vla_dashboard.engine import Engine  # noqa: E402
from vla_dashboard.learning.common import encode  # noqa: E402
from vla_dashboard.learning.policy import DEFAULT_CHECKPOINT, LearnedPolicy, tokens_for  # noqa: E402
from vla_dashboard.schemas import InstructionPayload  # noqa: E402

pytestmark = pytest.mark.skipif(not DEFAULT_CHECKPOINT.is_file(), reason="no trained checkpoint")

import importlib.util  # noqa: E402

SIMS = ["kinematic"] + [k for k in ("pybullet", "mujoco") if importlib.util.find_spec(k) is not None]

SCENE = [("cube", (220, 30, 30), (-0.22, 0.46, 0.025)), ("cylinder", (35, 45, 215), (-0.05, 0.46, 0.025)),
         ("sphere", (40, 200, 70), (0.12, 0.46, 0.025))]


@pytest.fixture(scope="module")
def policy():
    p = LearnedPolicy()
    p.load()
    return p


def _engine(sim):
    e = Engine(AppConfig(perception_mode="mock", brain_backend="learned", sim_backend=sim, sim_async_render=False))
    e.load()
    return e


def _run(e, text, max_steps=500):
    e.start_episode(InstructionPayload(text=text))
    for _ in range(max_steps):
        if e.tick(sync_perception=True).done:
            break
    for _ in range(15):
        e.sim.apply_delta(np.zeros(7))
    return e.object_positions(), e.sim.state()


@pytest.mark.parametrize("sim", SIMS)
def test_learned_policy_stacks_through_full_stack(sim):
    """Renderer -> perception -> learned policy -> controller -> physics, default scene."""
    e = _engine(sim)
    try:
        assert e.brain.policy.source == "learned"
        assert e.brain.describe()[1]  # the GUI shows "trained model …" in green
        objs, st = _run(e, "put the red cube on the blue cylinder")
        assert np.linalg.norm(objs["cube"][:2] - objs["cylinder"][:2]) < 0.025 and objs["cube"][2] > 0.07, objs
        assert st["holding"] is None
    finally:
        e.shutdown()


def test_learned_policy_uses_no_rules(monkeypatch):
    """Make every rule-based path explode: the learned policy must still do the task."""
    import vla_dashboard.brain.policies as pol
    import vla_dashboard.perception.pipeline as pipe

    def boom(*a, **k):
        raise AssertionError("rule-based code path used at inference")

    monkeypatch.setattr(pipe.SceneIndex, "resolve", boom)
    monkeypatch.setattr(pol, "plan_waypoints", boom)
    monkeypatch.setattr(pol.OKRobotScriptedPolicy, "infer", boom)
    e = _engine("kinematic")
    try:
        objs, st = _run(e, "pick up the green ball")
        assert st["holding"] == "sphere" and objs["sphere"][2] > 0.1
    finally:
        e.shutdown()


@pytest.mark.parametrize("text,expected", [
    ("pick up the red block", "cube"), ("grab the ball", "sphere"), ("lift the can", "cylinder"),
    ("take the green orb", "sphere"), ("get the blue tube", "cylinder"), ("pick up the box", "cube"),
])
def test_learned_grounding_follows_language(policy, text, expected):
    policy.reset()
    toks = tokens_for(SCENE)
    policy.step_features(encode(policy.tok, text, toks, np.array([0.1, 0.6, 0.25]), 1.0, False),
                         [t.label for t in toks])
    assert policy.targets[0] == expected


def test_learned_grounding_by_colour_without_labels(policy):
    """No OCR labels at all: 'red' must still find the red object."""
    toks = tokens_for([("", c, p) for _, c, p in SCENE])
    policy.reset()
    policy.step_features(encode(policy.tok, "pick up the red block", toks, np.array([0.1, 0.6, 0.25]), 1.0, False),
                         ["cube", "cylinder", "sphere"])
    assert policy.targets[0] == "cube"


def test_learned_policy_refuses_unknown_object(policy):
    toks = tokens_for(SCENE)
    policy.reset()
    for _ in range(3):
        if policy.done:
            break
        policy.step_features(encode(policy.tok, "pick up the purple banana", toks, np.array([0.1, 0.6, 0.25]), 1.0,
                                    False), [t.label for t in toks])
    assert policy.done and policy.failed


def test_learned_inference_is_fast(policy):
    feats = encode(policy.tok, "put the cube on the cylinder", tokens_for(SCENE), np.array([0.1, 0.6, 0.25]), 1.0,
                   False)
    t = time.perf_counter()
    for _ in range(50):
        policy.act(feats)
    assert (time.perf_counter() - t) / 50 < 0.005  # well under one 50 ms control tick


def test_missing_checkpoint_falls_back_loudly(caplog):
    from vla_dashboard.brain.vla_brain import VLABrain

    brain = VLABrain(AppConfig(brain_backend="learned", learned_checkpoint="/nonexistent/model.pt"))
    brain.load()
    assert brain.policy.source == "mock"
    assert "LEARNED POLICY UNAVAILABLE" in caplog.text
    brain.shutdown()
