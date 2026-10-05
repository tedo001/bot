"""LearnedPolicy: the trained transformer drives the robot. No rules at inference time."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np

from ..config import AppConfig
from .common import ACTION_SCALE, NONE_SLOT, ObjectToken, Tokenizer, encode, objects_from_scene

log = logging.getLogger(__name__)

DEFAULT_CHECKPOINT = Path(__file__).resolve().parent.parent / "assets" / "models" / "vla_act.pt"


class LearnedPolicy:
    source = "learned"

    def __init__(self, cfg: AppConfig | None = None, checkpoint: str | Path | None = None,
                 exec_horizon: int | None = None, threads: int = 2) -> None:
        cfg = cfg or AppConfig()
        self.path = Path(checkpoint or cfg.learned_checkpoint or DEFAULT_CHECKPOINT)
        self.exec_horizon = exec_horizon or cfg.learned_exec_horizon
        self.done_threshold = cfg.learned_done_threshold
        self.threads = threads
        self.model = self.tok = self.torch = None
        self.meta: dict = {}
        self.reset()

    # ------------------------------------------------------------------ lifecycle
    def load(self) -> None:
        import torch

        from .model import ActPolicyNet

        if not self.path.is_file():
            raise FileNotFoundError(f"no trained model at {self.path} (run: python -m vla_dashboard.learning.train)")
        ckpt = torch.load(self.path, map_location="cpu", weights_only=False)
        self.tok = Tokenizer(ckpt["vocab"])
        self.model = ActPolicyNet(**ckpt["model_cfg"])
        self.model.load_state_dict(ckpt["state_dict"])
        self.model.eval()
        self.meta = ckpt.get("meta", {})
        self.torch = torch
        torch.set_num_threads(self.threads)  # tiny model: more threads only add contention with perception
        t = time.perf_counter()
        self.act(encode(self.tok, "pick up the cube", [], np.zeros(3), 1.0, False))  # warm-up
        params = sum(p.numel() for p in self.model.parameters())
        log.info("learned policy loaded: %s (%.2fM params, vocab %d, warm-up %.1f ms)", self.path.name, params / 1e6,
                 len(self.tok), (time.perf_counter() - t) * 1e3)
        self.reset()

    def reset(self) -> None:
        self._done = False
        self._done_votes = 0
        self._calls = 0
        self._failed: str | None = None
        self._phase = "idle"
        self.last: dict = {}
        self.targets: tuple[str | None, str | None] = (None, None)  # shown in the GUI overlay

    @property
    def done(self) -> bool:
        return self._done

    @property
    def failed(self) -> str | None:
        return self._failed

    @property
    def phase(self) -> str:
        return self._failed or self._phase

    # ------------------------------------------------------------------ inference
    def act(self, feats: dict[str, np.ndarray]) -> dict:
        """One forward pass on encoded features -> denormalised action chunk + heads."""
        torch = self.torch
        with torch.inference_mode():
            batch = {k: torch.from_numpy(np.asarray(v))[None] for k, v in feats.items()
                     if k in ("tokens", "obj_feat", "obj_label", "obj_mask", "proprio")}
            actions, done, src, dst = self.model(batch["tokens"], batch["obj_feat"], batch["obj_label"],
                                                 batch["obj_mask"], batch["proprio"])
        src_p = torch.softmax(src[0], -1).numpy()
        dst_p = torch.softmax(dst[0], -1).numpy()
        return {"chunk": actions[0].numpy().astype(np.float64) * ACTION_SCALE,
                "p_done": float(torch.sigmoid(done[0])), "src": int(src_p.argmax()), "src_p": float(src_p.max()),
                "dst": int(dst_p.argmax()), "dst_p": float(dst_p.max())}

    def step_features(self, feats: dict[str, np.ndarray], labels: list[str]) -> np.ndarray:
        """Shared by the live app and closed-loop evaluation: model output -> executable actions."""
        out = self.act(feats)
        self.last = out
        self._calls += 1
        src = labels[out["src"]] if out["src"] != NONE_SLOT and out["src"] < len(labels) else None
        dst = labels[out["dst"]] if out["dst"] != NONE_SLOT and out["dst"] < len(labels) else None
        self._phase = "model→" + (src or "–") + (f"→{dst}" if dst else "") + f" (done {out['p_done']:.2f})"
        self.targets = (src, dst)
        if out["p_done"] > self.done_threshold:
            self._done_votes += 1
        else:
            self._done_votes = 0
        if self._done_votes >= 2:  # two consecutive "finished" predictions: stop
            self._done = True
            if self._calls <= 3 and src is None:
                self._failed = "model: no object in view matches the instruction"
            return np.zeros((1, 7))
        return out["chunk"][: self.exec_horizon]

    def infer(self, obs) -> np.ndarray:
        objs = objects_from_scene(obs.scene, obs.rgb)
        feats = encode(self.tok, obs.instruction, objs, obs.ee, obs.gripper, obs.holding is not None)
        return self.step_features(feats, [o.label or "object" for o in objs])


def tokens_for(labels_rgb_pos: list[tuple[str, tuple, tuple]]) -> list[ObjectToken]:
    """Convenience for scripts/tests: build object tokens from (label, rgb, xyz) tuples."""
    return [ObjectToken(lb, np.asarray(p, float), np.asarray(c, float), 1.0) for lb, c, p in labels_rgb_pos]
