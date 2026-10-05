"""Train the learned VLA policy by imitation, then evaluate it in closed loop.

    python -m vla_dashboard.learning.train                     # defaults used for the shipped model
    python -m vla_dashboard.learning.train --kinematic 2000 --pybullet 0 --epochs 20   # quick run

Pipeline: generate demonstrations in parallel (both simulators) → train the transformer
(L1 on action chunks + done BCE + grounding pointer CE) → closed-loop evaluation on new
random layouts with training and held-out phrasings, on both simulators, plus a full-stack
check through the real perception pipeline → save checkpoint + metrics JSON.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import multiprocessing as mp
import time
from pathlib import Path

import numpy as np

from .common import NONE_SLOT, encode, objects_from_state
from .data import OBJECTS, build_tokenizer, cameras, generate, sample_layout, sample_task, success, TaskSpec
from .policy import DEFAULT_CHECKPOINT, LearnedPolicy

log = logging.getLogger("train")


# ---------------------------------------------------------------- data
def collect(kind: str, episodes: int, workers: int, seed: int) -> dict[str, np.ndarray] | None:
    if episodes <= 0:
        return None
    per = max(1, math.ceil(episodes / (workers * 4)))
    jobs = [(kind, seed + i, min(per, episodes - i * per)) for i in range(math.ceil(episodes / per))]
    jobs = [j for j in jobs if j[2] > 0]
    t = time.perf_counter()
    with mp.get_context("spawn").Pool(workers) as pool:
        results = pool.map(generate, jobs)
    parts = [r[0] for r in results if r[0] is not None]
    kept, tried = sum(r[1] for r in results), sum(r[2] for r in results)
    data = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    log.info("%s: %d/%d teacher demos kept, %d samples (%.0fs)", kind, kept, tried, len(data["done"]),
             time.perf_counter() - t)
    return data


# ---------------------------------------------------------------- training
def train(data: dict[str, np.ndarray], vocab_size: int, epochs: int, batch: int, lr: float, seed: int,
          on_epoch=None, resume_path: Path | None = None):
    """``on_epoch(model, epoch, val)`` is called after every epoch (checkpointing). If ``resume_path``
    holds optimizer/scheduler state from an interrupted run, training continues from there."""
    import torch
    import torch.nn.functional as F

    from .model import ActPolicyNet

    torch.manual_seed(seed)
    n = len(data["done"])
    perm = np.random.default_rng(seed).permutation(n)
    n_val = max(512, n // 20)
    val_idx, tr_idx = perm[:n_val], perm[n_val:]
    tens = {k: torch.from_numpy(v) for k, v in data.items()}
    has_aux = "subgoal" in data
    model = ActPolicyNet(vocab_size, aux_dim=4 if has_aux else 0)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    steps = epochs * math.ceil(len(tr_idx) / batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=steps, pct_start=0.05)
    w = torch.exp(-0.15 * torch.arange(data["actions"].shape[1], dtype=torch.float32))
    w = (w / w.mean()).view(1, -1, 1)  # weight near-term actions more (they are the ones executed)

    def losses(idx):
        b = {k: v[idx] for k, v in tens.items()}
        act, done, src, dst, aux = model(b["tokens"], b["obj_feat"], b["obj_label"], b["obj_mask"], b["proprio"])
        l_act = (F.l1_loss(act, b["actions"], reduction="none") * w).mean()
        if aux is not None:  # subgoal: sharper sense of *where* to go -> more precise placing
            l_act = l_act + 0.5 * F.smooth_l1_loss(aux, b["subgoal"])
        l_done = F.binary_cross_entropy_with_logits(done, b["done"])
        l_ptr = F.cross_entropy(src, b["src"]) + F.cross_entropy(dst, b["dst"])
        acc = ((src.argmax(-1) == b["src"]).float().mean() + (dst.argmax(-1) == b["dst"]).float().mean()) / 2
        return l_act, l_done, l_ptr, acc

    start_ep = 0
    if resume_path is not None and resume_path.is_file():
        st = torch.load(resume_path, map_location="cpu", weights_only=False)
        model.load_state_dict(st["model"])
        opt.load_state_dict(st["opt"])
        sched.load_state_dict(st["sched"])
        start_ep = st["epoch"]
        log.info("resuming from epoch %d (%s)", start_ep, resume_path)

    t0 = time.perf_counter()
    v = [float("nan")] * 4
    for ep in range(start_ep, epochs):
        model.train()
        order = torch.from_numpy(np.random.default_rng(seed + ep).permutation(tr_idx))
        tot = 0.0
        for i in range(0, len(order), batch):
            l_act, l_done, l_ptr, _ = losses(order[i:i + batch])
            loss = l_act + 0.5 * l_done + 0.2 * l_ptr
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            tot += float(loss) * len(order[i:i + batch])
        model.eval()
        with torch.no_grad():
            v = [x.item() if hasattr(x, "item") else x for x in losses(torch.from_numpy(val_idx))]
        log.info("epoch %2d/%d  train %.4f | val act %.4f done %.4f ptr %.4f grounding-acc %.3f  (%.0fs)", ep + 1,
                 epochs, tot / len(order), v[0], v[1], v[2], v[3], time.perf_counter() - t0)
        if resume_path is not None:  # survive interruptions: everything needed to continue
            torch.save({"model": model.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(),
                        "epoch": ep + 1}, resume_path)
        if on_epoch is not None:
            on_epoch(model, ep + 1, {"val_action_l1": v[0], "val_done_bce": v[1], "val_pointer_ce": v[2],
                                     "val_grounding_acc": v[3]})
    return model, {"val_action_l1": v[0], "val_done_bce": v[1], "val_pointer_ce": v[2], "val_grounding_acc": v[3]}


# ---------------------------------------------------------------- closed-loop evaluation
def closed_loop(policy: LearnedPolicy, sim, camera, spec: TaskSpec, rng, label_dropout=0.0, max_steps=320):
    from ..config import AppConfig

    cfg = AppConfig()
    lim = np.concatenate([np.full(3, cfg.max_translation_step), np.full(3, cfg.max_rotation_step), [1.0]])
    sim.reset(layout=sample_layout(rng, spec), render_static=False)
    start = sim.state()
    policy.reset()
    steps = 0
    while steps < max_steps and not policy.done:
        st = sim.state()
        toks, _ = objects_from_state(st["objects"], st["holding"], camera, rng, label_dropout=label_dropout)
        feats = encode(policy.tok, spec.text, toks, st["ee"], st["gripper"], st["holding"] is not None)
        for a in policy.step_features(feats, [t.label for t in toks]):
            sim.apply_delta(np.clip(a, -lim, lim))
            steps += 1
    for _ in range(10):
        sim.apply_delta(np.zeros(7))  # let physics settle before judging
    return success(spec, start, sim.state()), steps


def evaluate(policy: LearnedPolicy, episodes: int, seed: int, include_pybullet: bool) -> dict:
    from .data import _get_sim

    rng = np.random.default_rng(seed)
    cams = cameras()
    results = {}
    sims = ["kinematic"] + (["pybullet"] if include_pybullet else [])
    for kind in sims:
        sim = _get_sim(kind)
        n = episodes
        for split, kw in (("train_phrasing", {}), ("heldout_phrasing", {"heldout": True}),
                          ("no_labels", {})):
            ok_by_kind: dict[str, list[bool]] = {}
            for _ in range(n):
                spec = sample_task(rng, **kw)
                ok, _ = closed_loop(policy, sim, cams[int(rng.integers(2))], spec, rng,
                                    label_dropout=1.0 if split == "no_labels" else 0.0)
                ok_by_kind.setdefault(spec.kind, []).append(ok)
            allv = [v for vs in ok_by_kind.values() for v in vs]
            results[f"{kind}/{split}"] = {"success": float(np.mean(allv)), "n": len(allv),
                                         **{k: round(float(np.mean(v)), 3) for k, v in ok_by_kind.items()}}
            log.info("eval %-30s success %.1f%%  %s", f"{kind}/{split}", 100 * np.mean(allv),
                     {k: f"{np.mean(v):.2f} (n={len(v)})" for k, v in ok_by_kind.items()})
        unk = []
        for i in range(10):
            spec = TaskSpec("unknown", ["pick up the purple banana", "grab the hammer", "put the mug on the cube",
                                        "lift the yellow duck", "place the phone next to the ball"][i % 5])
            ok, _ = closed_loop(policy, sim, cams[i % 2], spec, rng)
            unk.append(ok)
        results[f"{kind}/unknown_object_refusal"] = {"success": float(np.mean(unk)), "n": len(unk)}
        log.info("eval %-30s success %.1f%%", f"{kind}/unknown_object_refusal", 100 * np.mean(unk))
    return results


def full_stack_eval(checkpoint: Path, episodes: int, sim_kind: str) -> dict:
    """Through the real app path: renderer -> perception pipeline -> LearnedPolicy -> controller."""
    from ..config import AppConfig
    from ..engine import Engine
    from ..schemas import InstructionPayload

    cfg = AppConfig(perception_mode="mock", brain_backend="learned", sim_backend=sim_kind, sim_async_render=False,
                    learned_checkpoint=str(checkpoint))
    eng = Engine(cfg)
    eng.load()
    rng = np.random.default_rng(123)
    oks = []
    texts = ["put the red cube on the blue cylinder", "pick up the green ball", "place the sphere next to the cube",
             "stack the ball on the block", "grab the can", "put the cylinder beside the red box"]
    for i in range(episodes):
        text = texts[i % len(texts)]
        spec = _spec_from_text(text)
        layout = None if i < len(texts) else sample_layout(rng, spec)
        eng.sim.reset(layout=layout)
        eng.perception.invalidate()
        start = eng.sim.state()
        eng.start_episode(InstructionPayload(text=text))
        for _ in range(cfg.max_episode_steps):
            if eng.tick(sync_perception=True).done:
                break
        for _ in range(10):
            eng.sim.apply_delta(np.zeros(7))
        oks.append(success(spec, start, eng.sim.state()))
    eng.shutdown()
    res = {"success": float(np.mean(oks)), "n": len(oks)}
    log.info("eval full-stack/%-20s success %.1f%% (n=%d)", sim_kind, 100 * res["success"], len(oks))
    return res


def _spec_from_text(text: str) -> TaskSpec:  # evaluation bookkeeping only (judging success), never shown to the model
    from .data import OBJECT_PHRASES

    found = []
    for w in text.lower().replace(",", " ").split():
        for name, phrases in OBJECT_PHRASES.items():
            if w in {p.split()[-1] for p in phrases} and name not in found:
                found.append(name)
    if len(found) == 1:
        return TaskSpec("pick", text, found[0])
    kind = "stack" if (" on " in f" {text} " or "onto" in text) else "next_to"
    return TaskSpec(kind, text, found[0], found[1])


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kinematic", type=int, default=5000, help="teacher episodes in the kinematic sim")
    ap.add_argument("--pybullet", type=int, default=3000, help="teacher episodes in the PyBullet GP7 sim")
    ap.add_argument("--epochs", type=int, default=16)
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--workers", type=int, default=max(1, min(8, mp.cpu_count())))
    ap.add_argument("--eval-episodes", type=int, default=60)
    ap.add_argument("--full-stack-episodes", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=DEFAULT_CHECKPOINT)
    ap.add_argument("--work-dir", type=Path, default=Path(".vla_train"),
                    help="dataset cache + resume state (safe to delete)")
    ap.add_argument("--resume", action="store_true", help="continue an interrupted run from --work-dir")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    import torch

    tok = build_tokenizer()
    args.work_dir.mkdir(parents=True, exist_ok=True)
    cache = args.work_dir / f"demos_k{args.kinematic}_p{args.pybullet}_s{args.seed}.npz"
    if args.resume and cache.is_file():
        data = dict(np.load(cache))
        log.info("loaded cached demonstrations %s", cache)
    else:
        parts = [d for d in (collect("kinematic", args.kinematic, args.workers, args.seed),
                             collect("pybullet", args.pybullet, args.workers, args.seed + 100_000)) if d is not None]
        data = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
        np.savez(cache, **data)
    log.info("dataset: %d samples, vocab %d", len(data["done"]), len(tok))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    meta = {"trained": time.strftime("%Y-%m-%d %H:%M"), "samples": int(len(data["done"])),
            "teacher_episodes": {"kinematic": args.kinematic, "pybullet": args.pybullet}, "epochs": args.epochs,
            "objects": list(OBJECTS), "none_slot": NONE_SLOT}

    latest = args.work_dir / "latest.pt"

    def save(model, epoch: int, val: dict) -> None:
        """Usable checkpoint after every epoch, kept in the work dir: the shipped file at --out is
        only replaced once training and evaluation have finished."""
        meta.update(val, epochs_done=epoch)
        torch.save({"state_dict": model.state_dict(), "model_cfg": model.cfg, "vocab": tok.vocab, "meta": meta},
                   latest)

    resume = args.work_dir / "resume.pt"
    if not args.resume:
        resume.unlink(missing_ok=True)
    model, val = train(data, len(tok), args.epochs, args.batch, args.lr, args.seed, on_epoch=save,
                       resume_path=resume)
    meta.update(val)
    ckpt = {"state_dict": model.state_dict(), "model_cfg": model.cfg, "vocab": tok.vocab, "meta": meta}
    torch.save(ckpt, latest)

    policy = LearnedPolicy(checkpoint=latest)
    policy.load()
    meta["closed_loop"] = evaluate(policy, args.eval_episodes, args.seed + 7, include_pybullet=args.pybullet > 0)
    if args.full_stack_episodes > 0:
        meta["full_stack"] = {"kinematic": full_stack_eval(latest, args.full_stack_episodes, "kinematic")}
        if args.pybullet > 0:
            meta["full_stack"]["pybullet"] = full_stack_eval(latest, max(6, args.full_stack_episodes // 2),
                                                             "pybullet")
    ckpt["meta"] = meta
    torch.save(ckpt, args.out)  # ship only the finished, evaluated model
    args.out.with_suffix(".json").write_text(json.dumps(meta, indent=2))
    log.info("saved %s (+ %s)", args.out, args.out.with_suffix(".json").name)


if __name__ == "__main__":
    main()
