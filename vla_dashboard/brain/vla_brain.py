"""VLABrain: instruction + image -> next validated ActionCommand.

Latency strategy (the core of the "fast and reliable" requirement):

1. Action chunking: one inference yields H actions; the control loop executes
   them at control_hz without waiting on the model (same idea as openpi's
   ``ActionChunkBroker``).
2. Async prefetch: when ``prefetch_ratio`` of the chunk is consumed, the next
   inference starts on a background thread, so the model runs *while* the robot
   moves. With prefetch, the model's latency is hidden as long as it is shorter
   than (1 - prefetch_ratio) * H / control_hz.
3. Delay compensation: a prefetched chunk was computed from a slightly old state.
   The first k actions, where k is the number of actions executed since that
   observation was taken, are dropped, so the robot never replays motion.
4. Bounded waiting: if a chunk is late, the loop waits at most
   ``inference_timeout_s`` and then returns ``None``; the controller holds
   position (watchdog) instead of freezing the loop.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Callable

import numpy as np

from ..config import AppConfig
from ..schemas import ActionCommand, InstructionPayload
from .policies import Observation, Policy, make_policy

log = logging.getLogger(__name__)


class ChunkScheduler:
    def __init__(self, policy: Policy, prefetch_ratio: float, timeout_s: float) -> None:
        self.policy = policy
        self.prefetch_ratio, self.timeout_s = prefetch_ratio, timeout_s
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vla-infer")
        self.reset()

    def reset(self) -> None:
        if getattr(self, "_future", None) is not None:
            self._future.cancel()  # best effort; a running call finishes and is discarded
        self._chunk: np.ndarray | None = None
        self._cursor = 0
        self._executed = 0  # total actions handed out
        self._future: Future | None = None
        self._submitted_at = 0
        self.last_inference_ms = 0.0

    def _infer_timed(self, obs: Observation) -> tuple[np.ndarray, float]:
        t = time.perf_counter()
        chunk = np.atleast_2d(self.policy.infer(obs))
        return chunk, (time.perf_counter() - t) * 1e3

    def _submit(self, make_obs: Callable[[], Observation]) -> None:
        self._submitted_at = self._executed
        self._future = self._pool.submit(self._infer_timed, make_obs())

    def _install(self, chunk: np.ndarray, ms: float) -> None:
        stale = self._executed - self._submitted_at
        if chunk.shape[0] > 1 and stale > 0:
            chunk = chunk[min(stale, chunk.shape[0] - 1):]
        self._chunk, self._cursor, self.last_inference_ms = chunk, 0, ms

    def next_action(self, make_obs: Callable[[], Observation]) -> np.ndarray | None:
        exhausted = self._chunk is None or self._cursor >= self._chunk.shape[0]
        if exhausted:
            if self._future is None:
                if self.policy.done:
                    return None
                self._submit(make_obs)
            try:
                chunk, ms = self._future.result(timeout=self.timeout_s)
            except FutureTimeout:
                log.warning("VLA inference late (> %.1fs); holding", self.timeout_s)
                return None
            finally:
                if self._future is not None and self._future.done():
                    self._future = None
            self._install(chunk, ms)
        elif (self.prefetch_ratio > 0 and self._future is None and not self.policy.done
              and self._cursor >= self.prefetch_ratio * self._chunk.shape[0]):
            self._submit(make_obs)

        a =self._chunk[self._cursor]
        self._cursor += 1
        self._executed += 1
        return a

    @property
    def idle(self) -> bool:
        return self.policy.done and self._future is None and (
            self._chunk is None or self._cursor >= self._chunk.shape[0])

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


class VLABrain:
    def __init__(self, cfg: AppConfig, policy: Policy | None = None) -> None:
        self.cfg = cfg
        self.policy = policy or make_policy(cfg)
        # The scripted policy is closed-loop on perception, so it re-plans every chunk
        # without prefetch; learned remote policies benefit from prefetch.
        prefetch = cfg.prefetch_ratio if self.policy.source != "mock" else 0.0
        self.scheduler = ChunkScheduler(self.policy, prefetch, cfg.inference_timeout_s)
        self._lock = threading.Lock()
        self._instruction: InstructionPayload | None = None

    def load(self) -> None:
        self.policy.load()

    def set_instruction(self, payload: InstructionPayload) -> None:
        with self._lock:
            self._instruction = payload
            self.policy.reset()
            self.scheduler.reset()
        log.info("instruction[%s]: %r", payload.request_id, payload.text)

    def clear_instruction(self) -> None:
        with self._lock:
            self._instruction = None
            self.policy.reset()
            self.scheduler.reset()

    @property
    def instruction(self) -> InstructionPayload | None:
        return self._instruction

    @property
    def policy_backend_name(self) -> str:
        return self.cfg.brain_backend

    @property
    def done(self) -> bool:
        return self.scheduler.idle

    @property
    def phase(self) -> str:
        return self.policy.phase

    def step(self, make_obs: Callable[[str], Observation]) -> ActionCommand | None:
        """Compute the next action. ``make_obs`` builds the observation lazily: it is only
        called when an inference is actually issued (not every tick), saving the
        image resize/encode on ticks served from the current chunk."""
        with self._lock:
            instr = self._instruction
            if instr is None:
                return None
            raw = self.scheduler.next_action(lambda: make_obs(instr.text))
        if raw is None:
            return None
        try:
            return ActionCommand.from_array(raw, source=self.policy.source,
                                            inference_ms=self.scheduler.last_inference_ms)
        except ValueError as exc:  # NaN/inf from the model -> reject, hold
            log.error("invalid action from %s: %s", self.policy.source, exc)
            return None

    def shutdown(self) -> None:
        self.scheduler.shutdown()
