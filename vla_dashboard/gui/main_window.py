"""Main dashboard window."""

from __future__ import annotations

import collections
import json
import logging
import os
import sys
import time
from pathlib import Path

from pydantic import ValidationError
from PyQt6.QtCore import QProcess, Qt, QThreadPool, QTimer
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMainWindow, QPlainTextEdit, QProgressBar,
    QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

from ..brain.vla_brain import VLABrain
from ..config import AppConfig
from ..engine import Engine
from ..learning.policy import DEFAULT_CHECKPOINT
from ..schemas import InstructionPayload, RunStatus, SystemState
from ..workers import ControlWorker, LoaderTask, PerceptionWorker
from .frame_view import FrameView
from .overlays import OverlayFlags

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
USER_MODELS = PROJECT_ROOT / "models"  # models you train from the GUI land here
EXAMPLES = (
    "Put the red cube on the blue cylinder",
    "Pick up the green ball",
    "Place the sphere next to the cube",
    "Grab the blue can",
    "Go home",
)
TRAIN_PRESETS = (("Quick (~5-10 min)", "quick"), ("Full (~40 min, best)", "full"))
NOISY = ("b3Warning", "No inertial data", "pybullet build time", "tcpb3", "flangeb3", "tool0")


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


def _model_label(path: Path) -> str:
    """Combo label for a checkpoint, with its closed-loop score from the metrics sidecar."""
    name = "Shipped model" if path.resolve() == DEFAULT_CHECKPOINT.resolve() else path.stem
    try:
        meta = json.loads(path.with_suffix(".json").read_text())
        cl = meta.get("closed_loop", {})
        score = cl.get("kinematic/train_phrasing", {}).get("success")
        phys = [v["success"] for k, v in cl.items() if k.endswith("/train_phrasing") and not k.startswith("kin")]
        bits = [f"sim {score * 100:.0f}%" if score is not None else "",
                f"GP7 {phys[0] * 100:.0f}%" if phys else "", meta.get("trained", "")]
        return f"{name}  ({', '.join(b for b in bits if b)})"
    except (OSError, ValueError, KeyError):
        return name


class MainWindow(QMainWindow):
    def __init__(self, cfg: AppConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("VLA Robot Dashboard")
        self.resize(1320, 860)
        self.flags = OverlayFlags()
        self.engine = Engine(cfg)
        self.perception_worker: PerceptionWorker | None = None
        self.control_worker: ControlWorker | None = None
        self._pending_payload: InstructionPayload | None = None
        self._new_brain: VLABrain | None = None
        self._train: QProcess | None = None
        self._train_buf = ""
        self._train_saved: str | None = None
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
        self.instruction.setMaximumHeight(80)
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

        bbox = QGroupBox("Robot brain")
        fl = QFormLayout(bbox)
        self.backend = QComboBox()
        self.backend.addItems(["learned", "mock", "openvla", "openpi"])
        self.backend.setCurrentText(self.cfg.brain_backend)
        self.backend.setToolTip("learned = trained neural-network policy (runs locally, ~2 ms)\n"
                                "mock = rule-based planner (the teacher that generates training data)\n"
                                "openvla / openpi = clients for a separate GPU model server")
        fl.addRow("Policy", self.backend)
        self.model_combo = QComboBox()
        self.model_combo.setToolTip("Which trained checkpoint the 'learned' policy uses")
        self.model_combo.activated.connect(self._on_model_chosen)
        fl.addRow("Model", self.model_combo)
        self.brain_label = QLabel("-")
        self.brain_label.setWordWrap(True)
        fl.addRow("Driving", self.brain_label)
        lv.addWidget(bbox)
        self._refresh_models()

        trbox = QGroupBox("Train the policy (imitation learning)")
        tv = QVBoxLayout(trbox)
        trow = QHBoxLayout()
        self.train_preset = QComboBox()
        for label, key in TRAIN_PRESETS:
            self.train_preset.addItem(label, key)
        self.train_btn = QPushButton("Train new model")
        self.train_btn.clicked.connect(self._start_training)
        self.train_stop = QPushButton("Stop")
        self.train_stop.setEnabled(False)
        self.train_stop.clicked.connect(self._stop_training)
        trow.addWidget(self.train_preset, 1)
        trow.addWidget(self.train_btn)
        trow.addWidget(self.train_stop)
        tv.addLayout(trow)
        self.train_bar = QProgressBar()
        self.train_bar.setRange(0, 1000)
        self.train_bar.setValue(0)
        tv.addWidget(self.train_bar)
        self.train_status = QLabel("The rule-based teacher generates demonstrations, the network learns from them, "
                                   "is evaluated, and the new model is switched in automatically.")
        self.train_status.setWordWrap(True)
        tv.addWidget(self.train_status)
        lv.addWidget(trbox)

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

        scroll = QScrollArea()  # the left panel scrolls on small screens instead of squashing
        scroll.setWidget(left)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(360)
        scroll.setMaximumWidth(460)

        self.view = FrameView()
        self.console = QPlainTextEdit(readOnly=True)
        self.console.setMaximumBlockCount(3000)  # bounded: appending stays O(1) forever
        self.console.setFont(mono)
        self.console.setStyleSheet("QPlainTextEdit{background:#111418;color:#cfd8dc;}")

        right = QSplitter(Qt.Orientation.Vertical)
        right.addWidget(self.view)
        right.addWidget(self.console)
        right.setSizes([620, 200])
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(scroll)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        self.setCentralWidget(split)

        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._on_run)
        QShortcut(QKeySequence("Escape"), self, activated=lambda: self.estop.toggle())

    def _pick_example(self, i: int) -> None:
        if i > 0:
            self.instruction.setPlainText(self.examples.itemText(i))
        self.examples.setCurrentIndex(0)

    # ------------------------------------------------------------------ models
    def _refresh_models(self, select: Path | None = None) -> None:
        paths = [DEFAULT_CHECKPOINT] if DEFAULT_CHECKPOINT.is_file() else []
        if USER_MODELS.is_dir():
            paths += sorted(USER_MODELS.glob("*.pt"), key=lambda p: p.stat().st_mtime, reverse=True)
        current = select or Path(self.cfg.learned_checkpoint or DEFAULT_CHECKPOINT)
        self.model_combo.clear()
        for p in paths:
            self.model_combo.addItem(_model_label(p), str(p.resolve()))
        idx = self.model_combo.findData(str(current.resolve()))
        self.model_combo.setCurrentIndex(max(idx, 0))

    def _selected_checkpoint(self) -> str:
        return self.model_combo.currentData() or str(DEFAULT_CHECKPOINT.resolve())

    def _brain_identity(self, brain: VLABrain) -> tuple[str, str]:
        ckpt = ""
        if brain.cfg.brain_backend == "learned":
            ckpt = str(Path(brain.cfg.learned_checkpoint or DEFAULT_CHECKPOINT).resolve())
        return brain.cfg.brain_backend, ckpt

    def _update_brain_label(self, brain: VLABrain | None = None) -> None:
        text, is_model = (brain or self.engine.brain).describe()
        color = "#1e8449" if is_model else "#c0392b"
        self.brain_label.setText(f"<span style='color:{color}'><b>{text}</b></span>")

    def _on_model_chosen(self, _i: int) -> None:
        self.backend.setCurrentText("learned")
        if self.control_worker is not None and self.run_btn.isEnabled():
            self._switch_brain("learned", self._selected_checkpoint(), None)

    # ------------------------------------------------------------------ lifecycle
    def _run_loader(self, fn, on_done) -> None:
        task = LoaderTask(fn)
        task.signals.finished.connect(on_done)
        task.signals.failed.connect(self._on_load_failed)
        self._loader = task  # keep a reference so the signals object outlives the run
        self.run_btn.setEnabled(False)
        QThreadPool.globalInstance().start(task)

    def _on_load_failed(self, msg: str) -> None:
        if self._new_brain is not None:  # a backend switch failed: keep driving with the current brain
            self._new_brain, self._pending_payload = None, None
            self.backend.setCurrentText(self.engine.brain.cfg.brain_backend)
            log.error("could not switch the robot brain: %s", msg)
            self._set_status(RunStatus.IDLE)
        else:
            self._set_status(RunStatus.FAILED)
            log.error("model loading failed: %s", msg)
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
        self._update_brain_label()
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
        if self.control_worker is None:
            log.warning("models still loading")
            return
        backend = self.backend.currentText()
        want = (backend, self._selected_checkpoint() if backend == "learned" else "")
        if want != self._brain_identity(self.engine.brain):
            self._switch_brain(backend, want[1], payload)
            return
        self._start(payload)

    def _switch_brain(self, backend: str, checkpoint: str, payload: InstructionPayload | None) -> None:
        self._pending_payload = payload
        self.control_worker.end_episode()
        upd = {"brain_backend": backend}
        if backend == "learned":
            upd["learned_checkpoint"] = checkpoint
        new_brain = VLABrain(self.cfg.model_copy(update=upd))
        log.info("switching robot brain -> %s%s (loading)…", backend,
                 f" ({Path(checkpoint).name})" if checkpoint else "")
        self._set_status(RunStatus.LOADING)
        self._new_brain = new_brain
        self._run_loader(new_brain.load, self._on_backend_ready)  # slow part, worker thread

    def _on_backend_ready(self) -> None:
        new_brain, self._new_brain = self._new_brain, None

        def _swap():  # runs inside the control thread, between ticks
            old, self.engine.brain = self.engine.brain, new_brain
            old.shutdown()

        self.control_worker.submit(_swap)
        self._update_brain_label(new_brain)
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

    # ------------------------------------------------------------------ training
    def _start_training(self) -> None:
        if self._train is not None:
            return
        preset = self.train_preset.currentData()
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out = USER_MODELS / f"policy_{preset}_{stamp}.pt"
        work = PROJECT_ROOT / ".vla_train" / f"gui_{stamp}"
        cores = os.cpu_count() or 2
        spare = str(max(1, cores - 1))  # leave a core so the robot keeps moving smoothly
        args = ["-u", "-m", "vla_dashboard.learning.train", "--preset", preset, "--out", str(out),
                "--work-dir", str(work), "--workers", spare, "--threads", spare]
        args += os.environ.get("VLA_TRAIN_ARGS", "").split()  # power users: extra train.py options
        proc = QProcess(self)
        proc.setProgram(sys.executable)
        proc.setArguments(args)
        proc.setWorkingDirectory(str(PROJECT_ROOT))
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.readyReadStandardOutput.connect(self._on_train_output)
        proc.finished.connect(self._on_train_finished)
        self._train, self._train_buf, self._train_saved = proc, "", None
        self.train_bar.setValue(0)
        self.train_btn.setEnabled(False)
        self.train_stop.setEnabled(True)
        self.train_preset.setEnabled(False)
        self.train_status.setText(f"Starting {preset} training…")
        log.info("training started (%s preset) -> %s", preset, out.name)
        proc.start()

    def _on_train_output(self) -> None:
        if self._train is None:
            return
        self._train_buf += bytes(self._train.readAllStandardOutput()).decode("utf-8", errors="replace")
        *lines, self._train_buf = self._train_buf.split("\n")
        for line in (ln.strip() for ln in lines):
            if not line or any(n in line for n in NOISY):
                continue
            if line.startswith("@@progress"):
                _, frac, *msg = line.split(" ", 2)
                self.train_bar.setValue(int(float(frac) * 1000))
                self.train_status.setText(msg[0] if msg else "")
            elif line.startswith("@@saved"):
                self._train_saved = line.split(" ", 1)[1].strip()
            else:
                log.info("train: %s", line)

    def _on_train_finished(self, code: int, _status) -> None:
        saved, self._train = self._train_saved, None
        self.train_btn.setEnabled(True)
        self.train_stop.setEnabled(False)
        self.train_preset.setEnabled(True)
        if code != 0 or not saved:
            self.train_status.setText("Training stopped." if code else "Training finished without a model.")
            log.warning("training ended (exit code %s); see the console above", code)
            return
        path = Path(saved)
        self._refresh_models(select=path)
        self.train_bar.setValue(1000)
        self.train_status.setText(f"Done: {_model_label(path)}. Now driving the robot.")
        log.info("training complete: %s", _model_label(path))
        self.backend.setCurrentText("learned")
        if self.control_worker is not None:
            self._switch_brain("learned", str(path.resolve()), None)

    def _stop_training(self) -> None:
        if self._train is not None:
            log.info("stopping training…")
            self._train.kill()

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
        if self._train is not None:
            self._train.kill()
            self._train.waitForFinished(3000)
        if self.control_worker:
            self.control_worker.stop()
        if self.perception_worker:
            self.perception_worker.stop()
        self.engine.shutdown()
        logging.getLogger().removeHandler(self.log_handler)
        super().closeEvent(event)
