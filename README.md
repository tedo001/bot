# VLA Robot Dashboard

PyQt6 control dashboard and simulator for a Vision-Language-Action robot pipeline (Physical AI Robotics Challenge).

* Natural-language instruction box, **Run Simulation** / Stop / Reset / E-STOP, live camera stream with overlays, console log, telemetry.
* Simulator: **Yaskawa Motoman GP7** (or GP8) built from Yaskawa's CAD meshes (ROS-Industrial, BSD-3-Clause), on **MuJoCo** or **PyBullet**, with physics, IK and real grasping and stacking. Rendering runs on its own thread or process, so the 20 Hz control loop never waits on it. A dependency-free 2D simulator is the last-resort fallback.
* Perception: **PaddleOCR** (workspace labels) · **RT-DETR** via HF transformers (supportive detection + safety layer) · **RF-DETR** (instance segmentation → mask overlay + skeleton view). **No ultralytics** (AGPL).
* Brain: a **learned policy** drives the robot by default. It's a language-conditioned transformer trained by imitation learning (ACT-style action chunks), and it maps instruction + perceived objects + robot state to motor commands, with no hand-written rules at run time. Other backends: **OpenVLA** REST client, **openpi π₀** websocket client, and the rule-based **OK-Robot** planner (`mock`), which is the teacher that generated the training demonstrations.
* `RobotController` with E-STOP, safety hold, watchdog and rate limits. Pydantic v2 schemas at every boundary.
* Low latency: latest-frame hand-off, stride-scheduled models, O(1) scene index, action chunking with async prefetch, zero-copy frame display. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Run (Ubuntu or Windows, Python 3.10+)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py                       # Yaskawa GP7 on PyBullet, else MuJoCo, else the 2D sim
python run.py --robot gp8           # the shorter-reach GP8
python run.py --egl                 # GPU rendering + full-detail CAD meshes (Linux, GPU driver)
python run.py --sim kinematic       # lightweight numpy/OpenCV simulator
```

### Windows (PowerShell / PyCharm)

```powershell
py -3.12 -m venv .venv            # any Python 3.10–3.13
.venv\Scripts\Activate.ps1
pip install -r requirements.txt   # includes MuJoCo: the Yaskawa GP7 CAD robot works out of the box
python run.py
```

On Windows the GP7 runs on **MuJoCo** (prebuilt wheels). PyBullet is optional there and needs [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) before `pip install pybullet`. Choose the engine with `python run.py --sim mujoco` or `--sim pybullet`.

**PyCharm:** open the folder, set the interpreter to `.venv`, right-click `run.py` → *Run 'run'*.
Try "Put the red cube on the blue cylinder", "Pick up the green ball", "Place the sphere next to the cube". **Ctrl+Enter** runs, **Esc** toggles E-STOP.

### Troubleshooting

`run.py` checks the setup before starting and prints the fix. The common errors:

| Error | Cause | Fix |
|---|---|---|
| `No module named 'vla_dashboard'` | `run.py` opened without the project folder | `git clone -b sim https://github.com/tedo001/bot.git`, open the `bot` folder in PyCharm |
| `No module named 'PyQt6'` (or `pydantic_settings`, `cv2`, …) | PyCharm uses a different interpreter than the one you installed into | In PyCharm's Terminal: `python -m pip install -r requirements.txt`, or pick the `.venv` interpreter |
| `Could not load the Qt platform plugin "xcb" … cv2/qt/plugins` | `opencv-python` (GUI build) overrides Qt's plugin path | Handled automatically now; clean fix: `pip uninstall -y opencv-python && pip install opencv-python-headless` |
| `xcb-cursor0 or libxcb-cursor0 is needed` | missing Ubuntu library for Qt ≥ 6.5 | `sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1` |
| `dataclass() got an unexpected keyword argument 'slots'` | Python older than 3.10 | use a Python 3.10+ interpreter |
| `Microsoft Visual C++ 14.0 or greater is required` / `Failed building wheel for pybullet` (Windows) | no prebuilt pybullet for Windows on PyPI | not needed any more: `requirements.txt` installs MuJoCo for the GP7 instead |
| The robot is a flat 2D drawing, not the Yaskawa CAD model | no physics engine installed | `pip install mujoco` |
| Episodes fail with `ConnectTimeout … 127.0.0.1:8000` | Policy set to `openvla` / `openpi`, which need a separate GPU model server | choose the **learned** policy (runs locally), or start the server first |

## The learned policy

**Train from the app:** in the **Train the policy** panel pick *Quick* (a few minutes) or *Full* (about 40 minutes on a 4-core CPU) and press **Train new model**.
* Training runs in a separate process, so the robot keeps moving.
* The progress bar shows each stage: teacher demonstrations, training epochs, evaluation.
* When training finishes, the new model (saved in `models/`) is switched in automatically.
* The **Model** box lets you switch between the shipped model and anything you've trained.
* The **Driving** line always shows what controls the arm: green for a trained model, red if it ever falls back to rules.

From a terminal:

```bash
python -m vla_dashboard.learning.train                    # full preset: demos -> training -> evaluation
python -m vla_dashboard.learning.train --preset quick     # usable model in a few minutes
python -m vla_dashboard.learning.train --physics-sims mujoco --out models/my_policy.pt
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

Results of the shipped model (v2), closed loop on new random layouts:

| | Simple sim | GP7 on PyBullet | GP7 on MuJoCo |
|---|---|---|---|
| Training-style phrasings | 98.3% | 96.7% | 85.0% |
| Held-out phrasings (never seen) | 98.3% | 93.3% | 91.7% |
| No object labels (colour only) | 98.3% | 86.7% | 90.0% |
| Refuses unknown objects ("the banana") | 100% | 100% | 100% |
| Full app path (renderer → perception → model) | 24/24 | 11/12 | 11/12 |

60 episodes per row (10 for refusal). 31 of the 34 physics failures are one task: balancing an object on the ball. Every other task succeeds in 322 of 325 physics episodes. Both full-path failures are that task too ("put the blue tube on top of the green orb").

Balancing on the ball is a physics limit:
* In MuJoCo the object rolls off even when the scripted teacher releases it 0.1 mm from centre.
* PyBullet holds it if the release is within about 1 mm. The model sees only camera-derived positions and releases a median 6.6 mm off centre.

Training reports this task as `stack_on_ball`, separate from `stack`. Adding MuJoCo demonstrations to training (v3) made no measurable difference over 120 paired tasks per simulator, so v2 remains the shipped model.

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
  sim/mujoco_sim.py         Yaskawa GP7/GP8 sim on MuJoCo (Windows-friendly): physics + IK, render thread
  sim/pybullet_sim.py       Yaskawa GP7/GP8 sim on PyBullet: physics + IK in-process, rendering in a spawned process
  sim/scene.py              table, objects, labels, camera shared by both physics simulators
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
