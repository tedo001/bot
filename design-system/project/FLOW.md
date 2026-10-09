# System flow

How an operator moves through the studio, and how the robot's state moves underneath. The **SystemFlow** page (Components → Pages) draws the same thing as a diagram. Everything here maps to real code in `vla_dashboard/`; items marked *new* are additions this design proposes.

## 1. Start-up

| Step | What the operator sees | What runs | Exit |
|---|---|---|---|
| 1. Preflight | A checklist: Python ≥ 3.10, PyQt6, pydantic, OpenCV, MuJoCo/PyBullet, torch, Qt system libs. Each row OK / WARN / FAIL with the exact fix. | `run.py` checks | All required OK → 2. A missing optional engine offers **Install MuJoCo**. A FAIL stays here. |
| 2. Load | Studio opens. Status `LOADING`, Run disabled with tooltip "Models still loading". Console streams progress. | `Engine.load` in a `LoaderTask` (perception + brain) | Loaded → `IDLE`; error → `FAILED` with fix text. |
| 3. Ready | Camera stream and 3D cell live, telemetry at 10 Hz, status `IDLE`. | `PerceptionWorker` + `ControlWorker` at 20 Hz | — |

## 2. Run states

The controller's `RunStatus` drives the `StatusPill`, the status bar and which controls are enabled.

| State | Pill | Entered when | Leaves to | Run controls |
|---|---|---|---|---|
| IDLE | neutral | models ready, episode ended, scene reset | LOADING, RUNNING | Run, Step, Reset, Jog enabled |
| LOADING | `busy` + spinner | start-up, policy or model switch, a trained model being switched in | IDLE, FAILED | all disabled except E-STOP |
| RUNNING | `drive` | Run pressed with a valid instruction | SUCCEEDED, FAILED, STOPPED, SAFETY HOLD | Pause *(new)*, Stop, E-STOP; Jog disabled |
| SAFETY HOLD | `hold` + hazard banner | person in view (RT-DETR), watchdog, inference over `inference_timeout_s` | RUNNING (cause clears), STOPPED | Stop, E-STOP |
| SUCCEEDED | `ok` | policy predicts done twice in a row | IDLE (Run again or Reset) | Run again, Reset |
| FAILED | `danger` | no object matches the instruction, load error, episode exception | IDLE | Run, Reset; console opens on the error |
| STOPPED | neutral, outlined | Stop pressed | IDLE | Run, Reset |

**E-STOP is not a run state, it's a latch over all of them.** Pressing it (button or `Esc`) zeroes every command in `RobotController`, shows the `estop` banner, and keeps holding through episode ends and scene resets until the operator releases it. Releasing returns to whatever state was underneath, never straight into motion: a held RUNNING episode becomes STOPPED.

## 3. Episode flow (one instruction)

1. **Write**: type in the `InstructionBox` or pick an example. Validation runs as you type (`InstructionPayload`: 3–512 characters, must contain words, no control characters). An invalid instruction shows an inline error, and Run stays enabled but refuses with the reason.
2. **Preview** *(new, dry run)*: press `Preview` to ground the instruction without moving. The viewport marks SRC and DST, and the `TaskPlan` lists the phases. If nothing matches, the plan says so: "No object matches 'banana'".
3. **Brain check**: if the chosen policy/model differs from the loaded one, the studio goes `LOADING`, swaps the brain between control ticks, then continues.
4. **Run** (`Ctrl+Enter`): `RUNNING`. The `TaskPlan` advances through perceive → ground → approach → grasp → lift → move → place → release → retreat, with the policy's done probability shown live.
5. **End**: SUCCEEDED / FAILED / STOPPED. The episode is appended to **Episodes** *(new)* with instruction, duration, result, policy, model and a replay link.
6. **Reset scene** gives a new random layout and returns to IDLE.

Step mode *(new)*: `Step` (`F5`) executes one action chunk (8 actions) and pauses, so the operator can inspect each move.

## 4. Teach and jog *(new)*

1. Open the **Jog pendant** (floating window over the viewport) from the ribbon or with `J`. Only available in IDLE or STOPPED, with E-STOP released.
2. Pick a frame: Joint, World, Tool, User. Set speed override (default 10%, max 25% while jogging) and step (continuous, 10 mm, 1 mm, 0.1 mm / 5°, 1°, 0.1°).
3. Hold the deadman (`Space` or the hazard bar), then press +/− per axis. The bars show each joint against its limits and turn `hold` within 5% of a limit.
4. **Record pose** saves the TCP pose as `P[n]` into the program; **Go home** returns to the home pose.

## 5. Program flow *(new)*

Two ways to program, one result:

- **Natural language**: the instruction is the program; the learned policy chooses the motion.
- **Blocks**: a teach-pendant style list of lines (`MoveJ P[1] 50% FINE`, `Grip close`, `Detect 'red cube'`, `Wait 0.5 s`, `Run instruction "…"`). The `ProgramList` mixes taught poses with language steps, so a task can be "go to P[1], then *pick up the green ball*, then go home".

Programs save to the cell file with the scene and safety config. Running a program uses the same run states as above.

## 6. Training flow

1. **Train** workspace (or the Train panel): choose a preset, *Quick* (≈5–10 min) or *Full* (≈40 min on 4 cores).
2. **Train new model** starts a separate process; the robot keeps running. Progress shows three stages: teacher demonstrations → training epochs → closed-loop evaluation.
3. On success the model lands in `models/`, appears in the **Model registry** with its closed-loop scores (sim %, GP7 %), and is switched in automatically (`LOADING` → `IDLE`). The status bar's driving line turns `ok`.
4. **Stop** kills the process; nothing is switched in. A failure shows the exit code and opens the console.
5. *(new)* **Compare** two models on the same seeded layouts before switching.

## 7. Safety configuration *(new)*

1. **Safety** workspace lists every check in `SafetyChecks`: joint position limits, joint speed limit, Cartesian zone, stop prediction, person-in-view hold, watchdog, inference timeout, per-tick rate limit, collision detection.
2. Editing a value marks the row CHANGED (`hold`). The ribbon shows "Safety config changed: apply to run".
3. **Apply** asks for confirmation, verifies, and records a checksum shown in the status bar. While any row is CHANGED, Run is disabled with that reason.

## 8. Data flow (what the screens are showing)

```
Simulator (MuJoCo / PyBullet / 2D) ─render─► frame ─► Perception (RT-DETR · RF-DETR · OCR)
        ▲                                                  │ SceneIndex (objects, 3D positions)
        │ joint deltas                                     ▼
RobotController ◄── ActionCommand ◄── Brain (learned policy / OK-Robot / OpenVLA / openpi)
  E-STOP · safety hold · watchdog · rate limits                ▲ instruction (InstructionPayload)
        │                                                      │
        └──► SystemState (10 Hz) ──► Telemetry · StatusPill · TaskPlan · Viewport overlays
```

The control loop never waits on perception or rendering, so the UI must never imply it does. Show perception latency and loop rate separately (`Telemetry`), and show stale data as stale (muted value with its age) rather than freezing it.
