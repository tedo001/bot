# VLA Robot Dashboard

PyQt6 control dashboard and simulator for a Vision-Language-Action robot pipeline (Physical AI Robotics Challenge).

* Natural-language instruction box, **Run Simulation** / Stop / Reset / E-STOP, live camera stream with overlays, console log, telemetry.
* Perception: **PaddleOCR** (workspace labels) · **RT-DETR** via HF transformers (supportive detection + safety layer) · **RF-DETR** (instance segmentation → mask overlay + skeleton view). **No ultralytics** (AGPL).
* Brain: `VLABrain` with pluggable backends: **OK-Robot-style** scripted policy (default, no GPU), **OpenVLA** REST client, **openpi π₀** websocket client.
* `RobotController` with E-STOP, safety hold, watchdog and rate limits. Pydantic v2 schemas at every boundary.
* Low latency: latest-frame hand-off, stride-scheduled models, O(1) scene index, action chunking with async prefetch, zero-copy frame display. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Run (Ubuntu, Python 3.10+)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py                       # or: python -m vla_dashboard --backend mock
```

**PyCharm:** open the folder, set the interpreter to `.venv`, right-click `run.py` → *Run 'run'*.
Try "Put the red cube on the blue cylinder", "Pick up the green ball", "Place the sphere next to the cube". **Ctrl+Enter** runs, **Esc** toggles E-STOP.

If Qt reports a missing `xcb`/`libEGL` plugin on a fresh Ubuntu: `sudo apt install libegl1 libxkbcommon-x11-0 libxcb-cursor0`.

## Real models (optional)

```bash
pip install -r requirements-models.txt
python run.py --perception auto     # each model falls back to its mock if unavailable
python run.py --perception real     # fail loudly if a model can't load
```

| Backend | Start the server | Run the dashboard |
|---|---|---|
| OpenVLA | `python ../openvla/vla-scripts/deploy.py` | `python run.py --backend openvla` (`VLA_OPENVLA_URL=http://host:8000/act`) |
| openpi π₀ | `uv run ../openpi/scripts/serve_policy.py --env LIBERO` | `pip install -e ../openpi/packages/openpi-client && python run.py --backend openpi` |

You can also switch the backend from the GUI's *VLA backend* combo; the new brain loads in the background. Every setting in `vla_dashboard/config.py` can be overridden with a `VLA_*` environment variable, e.g. `VLA_CONTROL_HZ=30 VLA_SEG_STRIDE=2 python run.py`.

## Layout

```
run.py                      PyCharm entry point
vla_dashboard/
  config.py                 all latency/safety knobs (pydantic-settings)
  schemas.py                InstructionPayload, ActionCommand, Detection, RobotState, SystemState
  frame_bus.py              LatestSlot (latest-wins mailbox), FramePacket
  engine.py                 Qt-free core: sim → perception → brain → controller
  workers.py                ControlWorker / PerceptionWorker (QThread), LoaderTask (QRunnable)
  sim/simulator.py          kinematic tabletop sim + renderer (≈0.8 ms/frame)
  perception/               ocr.py, detector_rtdetr.py, segmenter_rfdetr.py, skeleton.py, pipeline.py
  brain/                    policies.py (OK-Robot / OpenVLA / openpi), vla_brain.py (ChunkScheduler)
  control/robot_controller.py   safety + home-robot adapter
  gui/                      main_window.py, frame_view.py (zero-copy), overlays.py
tests/                      schema, pipeline, scheduler and episode tests (pytest)
```

## Tests

```bash
pytest -q
```
