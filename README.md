# VLA Robot Dashboard

PyQt6 control dashboard and simulator for a Vision-Language-Action robot pipeline (Physical AI Robotics Challenge).

* Natural-language instruction box, **Run Simulation** / Stop / Reset / E-STOP, live camera stream with overlays, console log, telemetry.
* Simulator: **Yaskawa Motoman GP7** (or GP8) built from Yaskawa's CAD meshes (ROS-Industrial, BSD-3-Clause), with PyBullet physics, IK and real grasping and stacking. Rendering runs in its own process, so the 20 Hz control loop never waits on it. A dependency-free kinematic simulator is the fallback.
* Perception: **PaddleOCR** (workspace labels) · **RT-DETR** via HF transformers (supportive detection + safety layer) · **RF-DETR** (instance segmentation → mask overlay + skeleton view). **No ultralytics** (AGPL).
* Brain: a **learned policy** drives the robot by default. It's a language-conditioned transformer trained by imitation learning (ACT-style action chunks), and it maps instruction + perceived objects + robot state to motor commands, with no hand-written rules at run time. Other backends: **OpenVLA** REST client, **openpi π₀** websocket client, and the rule-based **OK-Robot** planner (`mock`), which is the teacher that generated the training demonstrations.
* `RobotController` with E-STOP, safety hold, watchdog and rate limits. Pydantic v2 schemas at every boundary.
* Low latency: latest-frame hand-off, stride-scheduled models, O(1) scene index, action chunking with async prefetch, zero-copy frame display. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Run (Ubuntu, Python 3.10+)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py                       # Yaskawa GP7 in PyBullet (falls back to the kinematic sim)
python run.py --robot gp8           # the shorter-reach GP8
python run.py --egl                 # GPU rendering + full-detail CAD meshes (Linux, GPU driver)
python run.py --sim kinematic       # lightweight numpy/OpenCV simulator
```

**PyCharm:** open the folder, set the interpreter to `.venv`, right-click `run.py` → *Run 'run'*.
Try "Put the red cube on the blue cylinder", "Pick up the green ball", "Place the sphere next to the cube". **Ctrl+Enter** runs, **Esc** toggles E-STOP.

If Qt reports a missing `xcb`/`libEGL` plugin on a fresh Ubuntu: `sudo apt install libegl1 libxkbcommon-x11-0 libxcb-cursor0`.

## The learned policy

```bash
python -m vla_dashboard.learning.train        # ~35 min on a 4-core CPU: demos -> training -> evaluation
python -m vla_dashboard.learning.train --kinematic 1500 --pybullet 0 --epochs 12   # ~4 min quick model
```

1. **Teacher demonstrations.** The rule-based planner is told the task directly and runs thousands of episodes:
   * random object layouts every episode
   * varied phrasings ("red block", "can", "orb", …)
   * noise injected into some executed actions, so the model sees how to recover
   * instructions naming objects that aren't there ("pick up the banana"), whose correct answer is "do nothing"
2. **Behaviour cloning.** The network learns from those demonstrations and outputs:
   * the next 8 actions
   * P(done)
   * which object the instruction refers to (source and destination)
3. **Closed-loop evaluation.** The model drives the robot on new layouts, in both simulators, through the real perception pipeline.

The checkpoint is `vla_dashboard/assets/models/vla_act.pt`, with its metrics in `vla_act.json`. In the dashboard the camera view marks the object the model chose (**SRC**) and its destination (**DST**), and the telemetry shows its done probability.

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
  sim/pybullet_sim.py       Yaskawa GP7/GP8 sim: physics + IK in-process, rendering in a spawned process
  sim/motoman_urdf.py       GP7/GP8 URDF (vendor kinematics + meshes) + parallel gripper
  sim/simulator.py          kinematic tabletop sim + renderer (≈0.8 ms/frame), fallback
  assets/motoman/           Yaskawa CAD meshes (BSD-3-Clause, see README there)
  perception/               ocr.py, detector_rtdetr.py, segmenter_rfdetr.py, skeleton.py, pipeline.py
  learning/                 learned policy: common.py (features), model.py, data.py (teacher demos), train.py, policy.py
  assets/models/            trained checkpoint + evaluation metrics
  brain/                    policies.py (OK-Robot teacher / OpenVLA / openpi), vla_brain.py (ChunkScheduler)
  control/robot_controller.py   safety + home-robot adapter
  gui/                      main_window.py, frame_view.py (zero-copy), overlays.py
tests/                      schema, pipeline, scheduler, episode tests on both simulators (pytest)
tools/decimate_meshes.py    rebuilds the smooth low-poly meshes used by the CPU renderer
```

## Tests

```bash
pytest -q
```
