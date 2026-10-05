"""Qt threading layer. Nothing here runs in the GUI thread except signal delivery.

Threads:
    GUI thread         paints frames, handles clicks. Never runs models.
    ControlWorker      fixed-rate loop: sim step -> brain -> controller; composes overlays
                       and emits frames at most display_fps times per second.
    PerceptionWorker   always processes the NEWEST frame (LatestSlot), skips stale ones.
    vla-infer          ThreadPoolExecutor inside ChunkScheduler (async prefetch).
    QThreadPool        one-off LoaderTask for slow model loading at start-up.

How frames reach the screen (zero copies after compositing):
    1. ``compose()`` returns a fresh (H, W, 3) uint8 numpy array in the control thread.
    2. ``frame_ready.emit(array)``: the signal type is ``object``, so Qt's queued
       connection only passes a Python reference across threads; pixels are not copied.
    3. ``FrameView.set_frame`` (GUI thread) stores the array and wraps the SAME memory
       in a ``QImage`` (Format_RGB888, bytesPerLine = 3 * W). Holding the array on the
       widget keeps the buffer alive for as long as the QImage points at it.
    4. ``paintEvent`` draws the QImage scaled to the widget. Frames that arrive faster
       than the screen refreshes just replace the reference (the old one is dropped).
"""

from __future__ import annotations

import logging
import queue
import time
import traceback
from typing import Callable

from PyQt6.QtCore import QObject, QRunnable, QThread, pyqtSignal

from .engine import Engine
from .gui.overlays import OverlayFlags, compose
from .schemas import RunStatus, SystemState

log = logging.getLogger(__name__)


class _LoaderSignals(QObject):
    finished = pyqtSignal()
    failed = pyqtSignal(str)


class LoaderTask(QRunnable):
    """Runs a slow callable (model download/initialisation) on the global QThreadPool."""

    def __init__(self, fn: Callable[[], None]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _LoaderSignals()

    def run(self) -> None:
        try:
            self.fn()
        except Exception as exc:  # noqa: BLE001
            log.error("load failed: %s\n%s", exc, traceback.format_exc())
            self.signals.failed.emit(str(exc))
        else:
            self.signals.finished.emit()


class PerceptionWorker(QThread):
    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.setObjectName("PerceptionWorker")
        self.engine = engine
        self.hz = 0.0
        self._running = True

    def run(self) -> None:
        last_seq, ema = 0, None
        slot = self.engine.frame_slot
        while self._running:
            seq, pkt = slot.wait_newer(last_seq, timeout=0.25)
            if slot.closed or not self._running:
                break
            if pkt is None or seq == last_seq:
                continue
            last_seq = seq
            t = time.perf_counter()
            try:
                self.engine.perception_slot.publish(self.engine.perception.process(pkt))
            except Exception:  # noqa: BLE001 - a bad frame must not kill the thread
                log.exception("perception error")
                continue
            dt = time.perf_counter() - t
            ema = dt if ema is None else 0.9 * ema + 0.1 * dt
            self.hz = 1.0 / max(ema, 1e-6)

    def stop(self) -> None:
        self._running = False
        self.engine.frame_slot.close()
        self.wait(2000)


class ControlWorker(QThread):
    frame_ready = pyqtSignal(object)  # np.ndarray (H, W, 3) uint8 RGB, see module docstring
    state_ready = pyqtSignal(object)  # SystemState
    episode_finished = pyqtSignal(str, str)  # status, message

    def __init__(self, engine: Engine, flags: OverlayFlags, perception: PerceptionWorker) -> None:
        super().__init__()
        self.setObjectName("ControlWorker")
        self.engine, self.flags, self.perception = engine, flags, perception
        self._cmds: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()
        self._running = True
        self.episode_active = False
        self._episode_steps = 0

    # Called from the GUI thread. The callable runs at the start of the next tick inside
    # the control thread, so the simulator is only ever touched by one thread (no locks).
    def submit(self, fn: Callable[[], None]) -> None:
        self._cmds.put(fn)

    def begin_episode(self, payload) -> None:
        def _go():
            self.engine.start_episode(payload)
            self.episode_active, self._episode_steps = True, 0
        self.submit(_go)

    def end_episode(self, reset_scene: bool = False) -> None:
        def _stop():
            (self.engine.reset_scene if reset_scene else self.engine.stop_episode)()
            if self.episode_active:
                self.episode_finished.emit(RunStatus.STOPPED.value, "stopped by operator")
            self.episode_active = False
        self.submit(_stop)

    def run(self) -> None:
        cfg = self.engine.cfg
        period = 1.0 / cfg.control_hz
        display_period = 1.0 / cfg.display_fps
        next_t = time.perf_counter()
        last_display = last_state = 0.0
        loop_ema = None
        prev = time.perf_counter()

        while self._running:
            while True:
                try:
                    self._cmds.get_nowait()()
                except queue.Empty:
                    break
                except Exception:  # noqa: BLE001
                    log.exception("command failed")

            try:
                res = self.engine.tick()
            except Exception:  # noqa: BLE001
                log.exception("control tick failed")
                self.engine.stop_episode()
                if self.episode_active:
                    self.episode_finished.emit(RunStatus.FAILED.value, "exception in control loop")
                self.episode_active = False
                time.sleep(period)
                continue

            now = time.perf_counter()
            dt, prev = now - prev, now
            loop_ema = dt if loop_ema is None else 0.9 * loop_ema + 0.1 * dt
            loop_hz = 1.0 / max(loop_ema, 1e-6)

            status = RunStatus.IDLE
            if self.episode_active:
                self._episode_steps += 1
                status = RunStatus.SAFETY_HOLD if self.engine.controller.safety_hold else RunStatus.RUNNING
                failed = getattr(self.engine.brain.policy, "failed", None)
                if res.done:
                    status = RunStatus.FAILED if failed else RunStatus.SUCCEEDED
                    self.episode_finished.emit(status.value, failed or f"done in {self._episode_steps} steps")
                    self.engine.stop_episode()
                    self.episode_active = False
                elif self._episode_steps >= cfg.max_episode_steps:
                    status = RunStatus.FAILED
                    self.episode_finished.emit(status.value, "max episode steps reached")
                    self.engine.stop_episode()
                    self.episode_active = False

            # Display path: only composite + emit when the screen can actually show it.
            if now - last_display >= display_period:
                last_display = now
                perc_ms = 1e3 / max(self.perception.hz, 1e-6)
                hud = (f"frame {res.packet.frame_id}  loop {loop_hz:4.1f} Hz  perc {perc_ms:5.1f} ms  "
                       f"vla {res.command.inference_ms:5.1f} ms  [{self.engine.brain.phase}]")
                self.frame_ready.emit(compose(res.packet.rgb, res.perception, self.flags, hud))
            if now - last_state >= 0.1:
                last_state = now
                self.state_ready.emit(SystemState(
                    status=status, robot=res.robot, last_action=res.command, phase=self.engine.brain.phase,
                    loop_hz=loop_hz, perception_hz=self.perception.hz,
                    stage_ms=dict(res.perception.summary.stage_ms) if res.perception else {},
                ))

            # Deadline scheduling: sleep until the next tick boundary (no drift). If we
            # are late, skip the missed ticks instead of bursting to catch up.
            next_t += period
            delay = next_t - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                next_t = time.perf_counter()

    def stop(self) -> None:
        self._running = False
        self.wait(2000)
