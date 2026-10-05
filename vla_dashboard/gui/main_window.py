"""Main dashboard window."""

from __future__ import annotations

import collections
import logging

from pydantic import ValidationError
from PyQt6.QtCore import Qt, QThreadPool, QTimer
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMainWindow, QPlainTextEdit,
    QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from ..brain.vla_brain import VLABrain
from ..config import AppConfig
from ..engine import Engine
from ..schemas import InstructionPayload, RunStatus, SystemState
from ..workers import ControlWorker, LoaderTask, PerceptionWorker
from .frame_view import FrameView
from .overlays import OverlayFlags

log = logging.getLogger(__name__)

EXAMPLES = (
    "Put the red cube on the blue cylinder",
    "Pick up the green ball",
    "Place the sphere next to the cube",
    "Go home",
)


class QtLogHandler(logging.Handler):
    """Collects log records from any thread into a deque; the GUI drains it on a timer.
    Batching avoids one cross-thread signal and one repaint per log line."""

    def __init__(self) -> None:
        super().__init__()
        self.buffer: collections.deque[str] = collections.deque(maxlen=5000)
        self.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)-7s %(name)s: %(message)s",
                                            "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        self.buffer.append(self.format(record))


class MainWindow(QMainWindow):
    def __init__(self, cfg: AppConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("VLA Robot Dashboard")
        self.resize(1280, 820)
        self.flags = OverlayFlags()
        self.engine = Engine(cfg)
        self.perception_worker: PerceptionWorker | None = None
        self.control_worker: ControlWorker | None = None
        self._pending_payload: InstructionPayload | None = None
        self._new_brain: VLABrain | None = None
        self._build_ui()

        self.log_handler = QtLogHandler()
        logging.getLogger().addHandler(self.log_handler)
        self._log_timer = QTimer(self, interval=100, timeout=self._drain_logs)
        self._log_timer.start()

        self._set_status(RunStatus.LOADING)
        log.info("loading perception + %s brain in background…", cfg.brain_backend)
        self._run_loader(self.engine.load, self._on_loaded)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        left = QWidget()
        lv = QVBoxLayout(left)

        box = QGroupBox("Natural-language instruction")
        bl = QVBoxLayout(box)
        self.instruction = QPlainTextEdit()
        self.instruction.setPlaceholderText("e.g. Put the red cube on the blue cylinder   (Ctrl+Enter to run)")
        self.instruction.setPlainText(EXAMPLES[0])
        self.instruction.setMaximumHeight(90)
        bl.addWidget(self.instruction)
        self.examples = QComboBox()
        self.examples.addItem("Examples…")
        self.examples.addItems(EXAMPLES)
        self.examples.activated.connect(self._pick_example)
        bl.addWidget(self.examples)

        row = QHBoxLayout()
        self.run_btn = QPushButton("▶  Run Simulation")
        self.run_btn.setStyleSheet("QPushButton{background:#1c4ecd;color:white;font-weight:bold;padding:8px;}"
                                   "QPushButton:disabled{background:#7a8bb8;}")
        self.run_btn.clicked.connect(self._on_run)
        self.stop_btn = QPushButton("■  Stop")
        self.stop_btn.clicked.connect(lambda: self.control_worker and self.control_worker.end_episode())
        self.reset_btn = QPushButton("⟲  Reset scene")
        self.reset_btn.clicked.connect(lambda: self.control_worker and self.control_worker.end_episode(True))
        for b in (self.run_btn, self.stop_btn, self.reset_btn):
            row.addWidget(b)
        bl.addLayout(row)
        self.estop = QCheckBox("E-STOP (hold all motion)")
        self.estop.setStyleSheet("QCheckBox{color:#c0392b;font-weight:bold;}")
        self.estop.toggled.connect(lambda on: setattr(self.engine.controller, "estop", on))
        bl.addWidget(self.estop)
        lv.addWidget(box)

        bbox = QGroupBox("VLA backend")
        fl = QFormLayout(bbox)
        self.backend = QComboBox()
        self.backend.addItems(["mock", "openvla", "openpi"])
        self.backend.setCurrentText(self.cfg.brain_backend)
        self.backend.setToolTip("mock = OK-Robot-style scripted policy (no GPU)\n"
                                "openvla = REST client for openvla/vla-scripts/deploy.py\n"
                                "openpi = websocket client for openpi/scripts/serve_policy.py")
        fl.addRow("Policy", self.backend)
        lv.addWidget(bbox)

        obox = QGroupBox("Overlays")
        ol = QVBoxLayout(obox)
        for attr, text in (("boxes", "Boxes + 3D position (RT-DETR / RF-DETR)"),
                           ("masks", "Segmentation masks (RF-DETR)"),
                           ("skeleton", "Skeleton view (objects + robot)"), ("ocr", "OCR labels (PaddleOCR)"),
                           ("hud", "HUD / latency")):
            cb = QCheckBox(text)
            cb.setChecked(getattr(self.flags, attr))
            cb.toggled.connect(lambda on, a=attr: setattr(self.flags, a, on))
            ol.addWidget(cb)
        lv.addWidget(obox)

        tbox = QGroupBox("Telemetry")
        tl = QFormLayout(tbox)
        self.t_status, self.t_phase, self.t_ee, self.t_rpy = QLabel("-"), QLabel("-"), QLabel("-"), QLabel("-")
        self.t_grip, self.t_action, self.t_rates, self.t_stages = QLabel("-"), QLabel("-"), QLabel("-"), QLabel("-")
        mono = QFont("Monospace")
        mono.setStyleHint(QFont.StyleHint.TypeWriter)
        for lab in (self.t_ee, self.t_rpy, self.t_action, self.t_stages):
            lab.setFont(mono)
            lab.setWordWrap(True)
        for k, v in (("Status", self.t_status), ("Phase", self.t_phase), ("EE xyz [m]", self.t_ee),
                     ("EE rpy [rad]", self.t_rpy), ("Gripper", self.t_grip), ("Action", self.t_action),
                     ("Rates", self.t_rates), ("Stages [ms]", self.t_stages)):
            tl.addRow(k, v)
        lv.addWidget(tbox)
        lv.addStretch(1)
        left.setMinimumWidth(330)
        left.setMaximumWidth(420)

        self.view = FrameView()
        self.console = QPlainTextEdit(readOnly=True)
        self.console.setMaximumBlockCount(3000)  # bounded: appending stays O(1) forever
        self.console.setFont(mono)
        self.console.setStyleSheet("QPlainTextEdit{background:#111418;color:#cfd8dc;}")

        right = QSplitter(Qt.Orientation.Vertical)
        right.addWidget(self.view)
        right.addWidget(self.console)
        right.setSizes([600, 200])
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        self.setCentralWidget(split)

        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._on_run)
        QShortcut(QKeySequence("Escape"), self, activated=lambda: self.estop.toggle())

    def _pick_example(self, i: int) -> None:
        if i > 0:
            self.instruction.setPlainText(self.examples.itemText(i))
        self.examples.setCurrentIndex(0)

    # ------------------------------------------------------------------ lifecycle
    def _run_loader(self, fn, on_done) -> None:
        task = LoaderTask(fn)
        task.signals.finished.connect(on_done)
        task.signals.failed.connect(self._on_load_failed)
        self._loader = task  # keep a reference so the signals object outlives the run
        self.run_btn.setEnabled(False)
        QThreadPool.globalInstance().start(task)

    def _on_load_failed(self, msg: str) -> None:
        self._set_status(RunStatus.FAILED)
        log.error("model loading failed: %s (switch the backend to 'mock' to keep working)", msg)
        self.run_btn.setEnabled(True)

    def _on_loaded(self) -> None:
        log.info("models ready; starting camera stream + control loop at %.0f Hz", self.cfg.control_hz)
        self.perception_worker = PerceptionWorker(self.engine)
        self.control_worker = ControlWorker(self.engine, self.flags, self.perception_worker)
        self.control_worker.frame_ready.connect(self.view.set_frame)
        self.control_worker.state_ready.connect(self._on_state)
        self.control_worker.episode_finished.connect(self._on_episode_finished)
        self.perception_worker.start()
        self.control_worker.start()
        self.run_btn.setEnabled(True)
        self._set_status(RunStatus.IDLE)

    def _on_run(self) -> None:
        if not self.run_btn.isEnabled():
            return
        try:
            payload = InstructionPayload(text=self.instruction.toPlainText())
        except ValidationError as exc:
            for e in exc.errors():
                log.error("invalid instruction: %s", e["msg"])
            return
        backend = self.backend.currentText()
        if self.control_worker is None:
            log.warning("models still loading")
            return
        if backend != self.engine.brain.policy_backend_name:
            self._pending_payload = payload
            self.control_worker.end_episode()
            cfg = self.cfg.model_copy(update={"brain_backend": backend})
            new_brain = VLABrain(cfg)
            log.info("switching VLA backend -> %s (loading)…", backend)
            self._set_status(RunStatus.LOADING)

            self._new_brain = new_brain
            self._run_loader(new_brain.load, self._on_backend_ready)  # slow part, worker thread
            return
        self._start(payload)

    def _on_backend_ready(self) -> None:
        new_brain, self._new_brain = self._new_brain, None

        def _swap():  # runs inside the control thread, between ticks
            old, self.engine.brain = self.engine.brain, new_brain
            old.shutdown()

        self.control_worker.submit(_swap)
        self.run_btn.setEnabled(True)
        self._set_status(RunStatus.IDLE)
        if self._pending_payload is not None:
            self._start(self._pending_payload)
            self._pending_payload = None

    def _start(self, payload: InstructionPayload) -> None:
        log.info("RUN [%s] %s", payload.request_id, payload.text)
        self.control_worker.begin_episode(payload)
        self._set_status(RunStatus.RUNNING)

    def _on_episode_finished(self, status: str, msg: str) -> None:
        lvl = logging.INFO if status == RunStatus.SUCCEEDED.value else logging.WARNING
        log.log(lvl, "episode %s: %s", status, msg)
        self._set_status(RunStatus(status))

    # ------------------------------------------------------------------ updates
    def _set_status(self, s: RunStatus) -> None:
        colors = {RunStatus.RUNNING: "#1c4ecd", RunStatus.SUCCEEDED: "#27ae60", RunStatus.FAILED: "#c0392b",
                  RunStatus.SAFETY_HOLD: "#e67e22", RunStatus.LOADING: "#8e44ad"}
        self.t_status.setText(f"<b style='color:{colors.get(s, '#555')}'>{s.value.upper()}</b>")
        self.statusBar().showMessage(f"status: {s.value}")

    def _on_state(self, st: SystemState) -> None:
        r = st.robot
        if st.status in (RunStatus.RUNNING, RunStatus.SAFETY_HOLD):
            self._set_status(st.status)
        self.t_phase.setText(st.phase or "-")
        self.t_ee.setText("{:+.3f} {:+.3f} {:+.3f}".format(*r.ee_position))
        self.t_rpy.setText("{:+.2f} {:+.2f} {:+.2f}".format(*r.ee_rpy))
        self.t_grip.setText(f"{r.gripper_opening:.2f} open" + (f" · holding <b>{r.holding}</b>" if r.holding else ""))
        if st.last_action is not None:
            a = st.last_action
            self.t_action.setText(f"d=({a.dx:+.3f},{a.dy:+.3f},{a.dz:+.3f}) g={a.gripper:+.2f} [{a.source}]")
        self.t_rates.setText(f"loop {st.loop_hz:.1f} Hz · perception {1e3 / max(st.perception_hz, 1e-6):.1f} ms · "
                             f"display {self.view.frames_shown} frames")
        self.t_stages.setText("  ".join(f"{k}:{v:.1f}" for k, v in st.stage_ms.items()) or "-")

    def _drain_logs(self) -> None:
        buf = self.log_handler.buffer
        if not buf:
            return
        lines = []
        while buf:
            lines.append(buf.popleft())
        self.console.appendPlainText("\n".join(lines))

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.control_worker:
            self.control_worker.stop()
        if self.perception_worker:
            self.perception_worker.stop()
        self.engine.shutdown()
        logging.getLogger().removeHandler(self.log_handler)
        super().closeEvent(event)
