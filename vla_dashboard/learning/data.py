"""Demonstration generation for imitation learning.

The rule-based OK-Robot planner is used ONLY here, as a teacher that is told the task
(object + destination) directly. The learned policy has to infer all of that from the raw
instruction text and perceived objects. Teaching signals per step:

    action chunk  : the teacher's next HORIZON actions from the current state
    done          : 1 once the task is complete (plus idle steps so the model learns to stop)
    src / dst     : which object slot the instruction refers to (auxiliary grounding loss)

Robustness tricks:
  * random object layouts every episode, random slot order, two camera geometries
  * DART-style noise: in some episodes executed actions are perturbed while labels stay the
    teacher's corrective actions, so the model learns to recover from its own errors
  * "unknown object" instructions (e.g. "pick up the banana") whose label is: do nothing, done
  * held-out phrasings (never used in training) to measure language generalisation
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace

import numpy as np

from ..brain.policies import OKRobotScriptedPolicy, Observation
from ..config import AppConfig
from .common import ACTION_SCALE, HORIZON, NONE_SLOT, Tokenizer, encode, objects_from_state

OBJECT_PHRASES = {
    "cube": ["cube", "red cube", "block", "red block", "box", "red box"],
    "cylinder": ["cylinder", "blue cylinder", "can", "blue can", "tube", "blue tube"],
    "sphere": ["sphere", "green sphere", "ball", "green ball", "orb", "green orb"],
}
TRAIN_TEMPLATES = {
    "pick": ["pick up the {a}", "grab the {a}", "lift the {a}", "take the {a}", "get the {a}", "pick the {a} up",
             "please pick up the {a}", "can you grab the {a}", "lift up the {a}"],
    "stack": ["put the {a} on the {b}", "place the {a} on top of the {b}", "stack the {a} on the {b}",
              "put the {a} onto the {b}", "place the {a} on the {b}", "move the {a} on top of the {b}"],
    "next_to": ["place the {a} next to the {b}", "put the {a} beside the {b}", "move the {a} near the {b}",
                "set the {a} next to the {b}", "place the {a} beside the {b}", "put the {a} next to the {b}"],
    "home": ["go home", "return home", "go back to the home position", "move to the home pose",
             "return to home position"],
}
# Never seen in training: new combinations of known words, and one unknown verb.
HELDOUT_TEMPLATES = {
    "pick": ["grasp the {a}", "please lift the {a}"],
    "stack": ["set the {a} on the {b}", "put the {a} on top of the {b}"],
    "next_to": ["move the {a} beside the {b}", "set the {a} near the {b}"],
    "home": ["go back home"],
}
UNKNOWN_NOUNS = ["banana", "apple", "hammer", "bottle", "mug", "phone", "screwdriver", "duck", "pen", "plate"]
UNKNOWN_ADJ = ["", "purple ", "yellow ", "black ", "white ", "orange "]
OBJECTS = ("cube", "cylinder", "sphere")
DEFAULT_LAYOUT = {"cube": (-0.22, 0.46), "cylinder": (-0.05, 0.46), "sphere": (0.12, 0.46)}
ROBOT_BASE_XY = np.array([0.30, 0.80])  # PyBullet GP7 base; keep objects outside its dead zone


# Verbs / filler words that may be blanked out during training (word dropout), so an
# unfamiliar verb ("grasp the cube") is not mistaken for an unknown object. Object words
# and relation words (on / next to / beside …) are never dropped: they carry the task.
FILLER_WORDS = {"pick", "up", "grab", "lift", "take", "get", "please", "can", "you", "put", "place", "stack",
                "move", "set", "the"}
SUBGOAL_SCALE = 0.05  # metres; subgoal offsets are labelled as clip(offset / scale, -3, 3)


@dataclass
class TaskSpec:
    kind: str  # pick | stack | next_to | home | unknown
    text: str
    src: str | None = None
    dst: str | None = None
    template: str = ""
    pa: str = ""
    pb: str = ""


def drop_filler_words(spec: TaskSpec, rng: np.random.Generator, p: float = 0.4) -> TaskSpec:
    """Replace some template filler words with an out-of-vocabulary word (-> <unk>)."""
    if not spec.template:
        return spec
    words = [("zzz" if (w in FILLER_WORDS and rng.random() < p) else w) for w in spec.template.split()]
    return replace(spec, text=" ".join(words).format(a=spec.pa, b=spec.pb))


def all_training_texts() -> list[str]:
    texts = []
    for kind, temps in TRAIN_TEMPLATES.items():
        for t in temps:
            for a in OBJECT_PHRASES.values():
                for pa in a:
                    for b in OBJECT_PHRASES.values():
                        for pb in b:
                            texts.append(t.format(a=pa, b=pb))
    texts += [f"pick up the {n}" for n in OBJECTS]  # make sure every label word is in the vocabulary
    return texts


def build_tokenizer() -> Tokenizer:
    return Tokenizer.build(all_training_texts())


def sample_task(rng: np.random.Generator, heldout: bool = False) -> TaskSpec:
    temps = HELDOUT_TEMPLATES if heldout else TRAIN_TEMPLATES
    r = rng.random()
    if not heldout and r < 0.06:
        noun = UNKNOWN_ADJ[rng.integers(len(UNKNOWN_ADJ))] + UNKNOWN_NOUNS[rng.integers(len(UNKNOWN_NOUNS))]
        kind = rng.choice(["pick", "stack", "next_to"])
        other = OBJECT_PHRASES[OBJECTS[rng.integers(3)]][rng.integers(6)]
        t = TRAIN_TEMPLATES[kind][rng.integers(len(TRAIN_TEMPLATES[kind]))]
        return TaskSpec("unknown", t.format(a=noun, b=other), template=t, pa=noun, pb=other)
    if r < 0.11:
        t = temps["home"][rng.integers(len(temps["home"]))]
        return TaskSpec("home", t, template=t)
    kind = ["pick", "stack", "next_to"][int(rng.integers(3))]
    a, b = rng.choice(OBJECTS, size=2, replace=False)
    pa = OBJECT_PHRASES[a][rng.integers(6)]
    pb = OBJECT_PHRASES[b][rng.integers(6)]
    t = temps[kind][rng.integers(len(temps[kind]))]
    return TaskSpec(kind, t.format(a=pa, b=pb), str(a), str(b) if kind != "pick" else None, template=t, pa=pa,
                    pb=pb)


def sample_layout(rng: np.random.Generator, spec: TaskSpec) -> dict[str, tuple[float, float]]:
    if rng.random() < 0.15:
        return dict(DEFAULT_LAYOUT)
    for _ in range(500):
        pts = {n: (float(rng.uniform(-0.30, 0.17)), float(rng.uniform(0.36, 0.62))) for n in OBJECTS}
        xy = {n: np.array(p) for n, p in pts.items()}
        if any(np.linalg.norm(xy[a] - xy[b]) < 0.11 for i, a in enumerate(OBJECTS) for b in OBJECTS[i + 1:]):
            continue
        if any(np.linalg.norm(v - ROBOT_BASE_XY) < 0.36 for v in xy.values()):
            continue
        if spec.kind == "next_to":  # the placement spot must be free, on the table and reachable
            side = 1.0 if xy[spec.src][0] > xy[spec.dst][0] else -1.0
            spot = xy[spec.dst] + np.array([0.07 * side, 0.0])
            third = next(n for n in OBJECTS if n not in (spec.src, spec.dst))
            if np.linalg.norm(spot - xy[third]) < 0.085 or not (-0.36 < spot[0] < 0.30):
                continue
            if np.linalg.norm(spot - ROBOT_BASE_XY) < 0.36:
                continue
        return pts
    return dict(DEFAULT_LAYOUT)


def success(spec: TaskSpec, start: dict, end: dict) -> bool:
    objs = end["objects"]
    if spec.kind == "pick":
        return end["holding"] == spec.src and objs[spec.src][2] > 0.10
    if spec.kind == "stack":
        a, b = objs[spec.src], objs[spec.dst]
        return np.linalg.norm(a[:2] - b[:2]) < 0.025 and a[2] > b[2] + 0.03 and end["holding"] is None
    if spec.kind == "next_to":
        d = np.linalg.norm(objs[spec.src][:2] - objs[spec.dst][:2])
        return 0.045 < d < 0.11 and objs[spec.src][2] < 0.05 and end["holding"] is None
    if spec.kind == "home":
        return np.linalg.norm(end["ee"] - np.array([0.10, 0.60, 0.25])) < 0.02
    # unknown: nothing may move
    return all(np.linalg.norm(objs[n] - start["objects"][n]) < 0.01 for n in objs) and end["holding"] is None


def _slot(names: list[str], name: str | None) -> int:
    return names.index(name) if name in names else NONE_SLOT


def demo_episode(sim, camera, tok: Tokenizer, spec: TaskSpec, rng: np.random.Generator, noise: float = 0.0,
                 idle_steps: int = 8, max_steps: int = 250) -> list[dict] | None:
    """Run the teacher on ``sim`` and record (features, labels) for every step."""
    cfg = AppConfig(action_horizon=1)
    lim = np.concatenate([np.full(3, cfg.max_translation_step), np.full(3, cfg.max_rotation_step), [1.0]])
    sim.reset(layout=sample_layout(rng, spec), render_static=False)
    start = sim.state()
    expert = OKRobotScriptedPolicy(cfg)
    if spec.kind == "home":
        expert.set_task("home")
    elif spec.kind in ("pick", "stack", "next_to"):
        objs = start["objects"]
        dst = objs[spec.dst] if spec.dst else None
        expert.set_task(spec.kind, objs[spec.src], dst)
    drop = ()
    if spec.kind != "unknown" and rng.random() < 0.04:  # occasionally a non-target object is not detected
        others = [n for n in OBJECTS if n not in (spec.src, spec.dst)]
        drop = (others[int(rng.integers(len(others)))],)
    samples = []

    def record(st, chunk: np.ndarray, done: float) -> None:
        toks, names = objects_from_state(st["objects"], st["holding"], camera, rng, drop_names=drop)
        f = encode(tok, spec.text, toks, st["ee"], st["gripper"], st["holding"] is not None)
        f["actions"] = (chunk / ACTION_SCALE).astype(np.float32)
        f["done"] = np.float32(done)
        # Auxiliary target: where the gripper should be heading right now (subgoal) + gripper target.
        wp = expert.current_waypoint() if spec.kind != "unknown" and not done else None
        sub = np.zeros(4, np.float32)
        if wp is not None:
            if wp[0] is not None:
                sub[:3] = np.clip((wp[0] - st["ee"]) / SUBGOAL_SCALE, -3, 3)
            sub[3] = wp[1]
        else:
            sub[3] = 0.0 if st["holding"] else 1.0
        f["subgoal"] = sub
        f["src"] = _slot(names, spec.src)
        f["dst"] = _slot(names, spec.dst)
        samples.append(f)

    if spec.kind != "unknown":
        for _ in range(max_steps):
            if expert.done:
                break
            st = sim.state()
            obs = Observation(rgb=None, instruction=spec.text, ee=st["ee"], rpy=st["rpy"], gripper=st["gripper"],
                              holding=st["holding"], scene=None)
            teacher = copy.deepcopy(expert)
            teacher.horizon = HORIZON
            part = teacher.infer(obs)
            chunk = np.zeros((HORIZON, 7))
            chunk[: len(part)] = part
            record(st, chunk, 0.0)
            a = expert.infer(obs)[0].copy()
            if noise > 0:
                a[:3] += rng.normal(0.0, noise, 3)
            sim.apply_delta(np.clip(a, -lim, lim))
        else:
            return None
    for _ in range(idle_steps):  # task complete (or impossible): hold still and report done
        st = sim.state()
        record(st, np.zeros((HORIZON, 7)), 1.0)
        sim.apply_delta(np.zeros(7))
    end = sim.state()
    return samples if success(spec, start, end) else None


def stack_samples(samples: list[dict]) -> dict[str, np.ndarray]:
    return {k: np.stack([s[k] for s in samples]) for k in samples[0]}


# ---------------------------------------------------------------- worker entry point
_SIMS: dict = {}


def _get_sim(kind: str):
    if kind not in _SIMS:
        if kind == "pybullet":
            from ..sim.pybullet_sim import PyBulletSim

            _SIMS[kind] = PyBulletSim(async_render=False)
        elif kind == "mujoco":
            from ..sim.mujoco_sim import MuJoCoSim

            _SIMS[kind] = MuJoCoSim(async_render=False)  # demos / evaluation never render
        else:
            from ..sim.simulator import TabletopSim

            _SIMS[kind] = TabletopSim()
    return _SIMS[kind]


def cameras():
    from ..sim.scene import CAMERA
    from ..sim.simulator import PinholeCamera

    return [PinholeCamera(640, 480), PinholeCamera(640, 480, **CAMERA)]


def generate(args: tuple[str, int, int]) -> tuple[dict[str, np.ndarray] | None, int, int]:
    """Worker: (sim kind, seed, n_episodes) -> stacked samples, episodes kept, episodes tried."""
    kind, seed, n = args
    rng = np.random.default_rng(seed)
    sim = _get_sim(kind)
    tok = build_tokenizer()
    cams = cameras()
    out, kept = [], 0
    for _ in range(n):
        spec = sample_task(rng)
        if rng.random() < 0.3:
            spec = drop_filler_words(spec, rng)
        noise = 0.004 if rng.random() < 0.5 else 0.0
        ep = demo_episode(sim, cams[int(rng.integers(2))], tok, spec, rng, noise=noise)
        if ep:
            out.extend(ep)
            kept += 1
    return (stack_samples(out) if out else None), kept, n

