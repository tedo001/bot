"""Model inputs: tokenizer + feature encoding. One code path for training AND inference.

The policy sees what the robot sees, never simulator internals:
  * the instruction as word tokens (vocabulary learned from the training phrasings),
  * one token per object found by the perception pipeline: 3D position (lifted from the
    2D box exactly as ``PerceptionPipeline`` does), its offset from the gripper, colour
    chromaticity + brightness from the camera image, detection score and the label text
    that OCR / the detector attached to it,
  * proprioception: gripper position, gripper opening, "object in gripper" signal.

``objects_from_scene`` builds object tokens from a live ``SceneIndex`` + camera frame;
``objects_from_state`` synthesises the same tokens from simulator state for training,
including the same 2D->3D lifting error, colour/lighting changes, label dropout and slot
shuffling the real pipeline produces. Keeping both here is what makes the trained
policy work on live perception.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

PAD, UNK = 0, 1
SPECIALS = ("<pad>", "<unk>")
MAX_TOKENS = 12
MAX_OBJECTS = 6
NONE_SLOT = MAX_OBJECTS  # pointer-head index meaning "no object"
HORIZON = 8  # actions predicted per inference (action chunk)
ACT_DIM = 7
REL_SCALES = (0.015, 0.05)  # metres: fine-scale views of the object-gripper offset (tanh-squashed)
FOURIER_FREQS = (1.0, 3.0, 9.0, 27.0)  # cycles per metre for the gripper position encoding
OBJ_DIM = 11 + 3 * len(REL_SCALES)  # abs xyz, offset (coarse + fine), chromaticity, brightness, score
PROPRIO_DIM = 5 + 3 * 2 * len(FOURIER_FREQS)  # xyz, opening, holding + Fourier features of xyz

POS_CENTER = np.array([0.0, 0.6, 0.1])
POS_SCALE = 0.3
ACTION_SCALE = np.array([0.02, 0.02, 0.02, 0.15, 0.15, 0.15, 1.0])  # normalised action = raw / scale
OBJECT_PLANE_Z = 0.025  # same plane PerceptionPipeline lifts boxes onto

# Nominal rendered colours (RGB); training jitters brightness and noise around these.
NOMINAL_RGB = {"cube": (220, 30, 30), "cylinder": (35, 45, 215), "sphere": (40, 200, 70)}
GRIPPER_RGB = np.array([205.0, 205.0, 200.0])


def words(text: str) -> list[str]:
    return re.findall(r"[a-z]+", text.lower())


class Tokenizer:
    def __init__(self, vocab: list[str]) -> None:
        self.vocab = list(vocab)
        self.index = {w: i for i, w in enumerate(self.vocab)}

    @classmethod
    def build(cls, texts) -> Tokenizer:
        seen = sorted({w for t in texts for w in words(t)})
        return cls([*SPECIALS, *seen])

    def id(self, word: str) -> int:
        return self.index.get(word.lower(), UNK)

    def encode(self, text: str) -> np.ndarray:
        ids = [self.id(w) for w in words(text)][:MAX_TOKENS]
        out = np.full(MAX_TOKENS, PAD, np.int64)
        out[: len(ids)] = ids
        return out

    def __len__(self) -> int:
        return len(self.vocab)


@dataclass(slots=True)
class ObjectToken:
    label: str  # text attached by OCR / detector ("" or unknown words are fine)
    position: np.ndarray  # (3,) metres, as perceived
    rgb: np.ndarray  # (3,) mean colour 0..255
    score: float


def encode(tok: Tokenizer, text: str, objects: list[ObjectToken], ee: np.ndarray, gripper: float,
           holding: bool) -> dict[str, np.ndarray]:
    ee = np.asarray(ee, np.float64)
    feat = np.zeros((MAX_OBJECTS, OBJ_DIM), np.float32)
    label = np.full(MAX_OBJECTS, PAD, np.int64)
    mask = np.zeros(MAX_OBJECTS, bool)
    for i, o in enumerate(objects[:MAX_OBJECTS]):
        pos = np.asarray(o.position, np.float64)
        rgb = np.asarray(o.rgb, np.float64)
        s = rgb.sum() + 1e-6
        feat[i, 0:3] = (pos - POS_CENTER) / POS_SCALE
        feat[i, 3:6] = (pos - ee) / POS_SCALE
        feat[i, 6:9] = rgb / s  # chromaticity: invariant to lighting brightness
        feat[i, 9] = s / (3 * 255.0)
        feat[i, 10] = o.score
        for k, sc in enumerate(REL_SCALES):  # multi-scale offset: precise near the object, bounded far away
            feat[i, 11 + 3 * k: 14 + 3 * k] = np.tanh((pos - ee) / sc)
        ws = words(o.label)
        label[i] = tok.id(ws[-1]) if ws else UNK
        mask[i] = True
    proprio = np.zeros(PROPRIO_DIM, np.float32)
    proprio[0:3] = (ee - POS_CENTER) / POS_SCALE
    proprio[3] = gripper
    proprio[4] = float(holding)
    ang = 2 * np.pi * np.outer(FOURIER_FREQS, ee).ravel()  # NeRF-style encoding: fine position detail
    proprio[5:] = np.concatenate([np.sin(ang), np.cos(ang)])
    return {"tokens": tok.encode(text), "obj_feat": feat, "obj_label": label, "obj_mask": mask, "proprio": proprio}


def objects_from_scene(scene, rgb: np.ndarray | None) -> list[ObjectToken]:
    """Live path: object tokens from the perception ``SceneIndex`` and the camera frame."""
    out = []
    if scene is None:
        return out
    for o in scene.objects.values():
        col = np.array([128.0, 128.0, 128.0])
        if rgb is not None:
            b = o.box
            cx, cy = b.center
            hw, hh = max(1.0, (b.x2 - b.x1) * 0.25), max(1.0, (b.y2 - b.y1) * 0.25)
            crop = rgb[max(0, int(cy - hh)): int(cy + hh) + 1, max(0, int(cx - hw)): int(cx + hw) + 1]
            if crop.size:
                col = crop.reshape(-1, 3).mean(axis=0)
        out.append(ObjectToken(o.name, np.asarray(o.position, np.float64), col, float(o.score)))
    return out


def objects_from_state(objects: dict[str, np.ndarray], holding: str | None, camera, rng: np.random.Generator,
                       label_dropout: float = 0.25, pixel_noise: float = 1.5,
                       drop_names: tuple[str, ...] = ()) -> tuple[list[ObjectToken], list[str]]:
    """Training path: synthesise perception-like object tokens from simulator state.
    Returns the tokens and the true object name of each slot (for pointer labels)."""
    toks, names = [], []
    for name, pos in objects.items():
        if name in drop_names:
            continue
        uv, _ = camera.project(np.asarray(pos, np.float64)[None])
        u, v = uv[0] + rng.normal(0.0, pixel_noise, 2)
        p = np.array(camera.deproject_to_plane(u, v, OBJECT_PLANE_Z))  # same lifting error as live perception
        col = np.array(NOMINAL_RGB.get(name, (128, 128, 128)), np.float64) * rng.uniform(0.55, 1.2)
        col += rng.normal(0.0, 12.0, 3)
        if holding == name and rng.random() < 0.5:  # fingers partly cover a held object
            col = 0.65 * col + 0.35 * GRIPPER_RGB
        label = name if rng.random() >= label_dropout else rng.choice(["", "object", "cup", "sports ball", "box"])
        toks.append(ObjectToken(str(label), p, np.clip(col, 0, 255), float(rng.uniform(0.6, 1.0))))
        names.append(name)
    order = rng.permutation(len(toks))
    return [toks[i] for i in order], [names[i] for i in order]
