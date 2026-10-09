# Screens

Six workspaces share one shell: `Ribbon` on top, docks left and right, the viewport in the middle, console at the bottom and `StatusBar` last. Switching workspace swaps the ribbon's tool groups and the docks' panels; the viewport, E-STOP, status pill and status bar stay put. Items marked *new* go beyond the current PyQt dashboard.

## Workcell

Set up the cell. The **Workcell** page shows it assembled.

- **Ribbon tools:** Robot (GP7 / GP8), Engine (MuJoCo / PyBullet / 2D), Add object *(new)*, Frames *(new)*, Camera, Reset scene, View (iso, top, front, fit).
- **Left dock:** `CellTree`, showing the controller, robot, tool and user frames, objects (with SRC/DST badges while a plan exists), cameras and the table. Under it `PropertyInspector` for the selection: location X Y Z (mm) and W P R (deg), relative-to frame, appearance, visibility, collision detection.
- **Viewport:** 3D cell with grid, view cube (top-right), axis triad (bottom-left), selection gizmo *(new)*, overlays (boxes, masks, skeleton, OCR, HUD).
- **Right dock:** `InstructionBox`, `RunControls`, `TaskPlan`.

## Program *(new)*

Write and edit what the robot does.

- **Ribbon tools:** New line, Record pose, Touch up, Insert instruction, Preview (dry run), Save.
- **Left dock:** program list (programs in the cell) and the instruction palette: Motion (MoveJ, MoveL), Gripper, Perception (Detect), Flow (Wait, If, Call), Language (Run instruction).
- **Centre:** viewport above, `ProgramList` below it in a split. The current line is highlighted while running.
- **Right dock:** `JogPanel` docked (or floating), `PoseReadout`.

## Run

Watch and control an episode. This is what the current dashboard is.

- **Ribbon tools:** Run, Step, Pause, Stop, Reset, View: 3D / Camera / Split *(new)*.
- **Centre:** camera frame with overlays (SRC/DST, boxes, masks, skeleton, OCR, HUD); split view shows camera beside the 3D cell.
- **Right dock:** `InstructionBox`, `RunControls`, `TaskPlan`, `Telemetry`, overlay `Toggle`s.
- **Bottom:** `Console`; Episodes tab *(new)* with history and replay.

## Safety *(new)*

Configure and verify the safety layer.

- **Ribbon tools:** Apply, Revert, Verify, Export report.
- **Centre:** viewport showing the Cartesian zone and joint-limit arcs.
- **Right dock:** `SafetyChecks` (each row OK / CHANGED / FAULT, a detail line and the limit value), then the selected check's settings form.
- Status bar shows the safety checksum.

## Train

Teach the policy and choose what drives the arm.

- **Ribbon tools:** Train new model, Stop, Compare *(new)*, Open models folder.
- **Left dock:** `ModelRegistry`, every checkpoint with closed-loop scores, date and source; the active one marked "Driving".
- **Centre:** the `TrainingProgress` stages (demonstrations → epochs → evaluation) with the current stage's numbers; evaluation results as a table per simulator and phrasing set.
- **Right dock:** brain settings: policy (learned, mock, openvla, openpi), model, server URL for remote policies.

## Diagnostics *(new)*

See why it's slow or failing.

- **Centre:** `Telemetry` at full width: loop Hz against the 20 Hz target, perception ms, stage timings against the 50 ms tick budget, render fps.
- **Right dock:** perception model status (RT-DETR, RF-DETR, PaddleOCR: real / mock, stride, last latency) and the preflight checklist again.
- **Bottom:** `Console` filtered to warnings and errors.

## Dialogs

- **Preflight**: the start-up checklist (see System flow §1).
- **Confirm**: names the object and the consequence; the destructive button uses `danger`, and the safe choice is the default focus.
- **E-STOP banner**: full-width `estop` bar under the ribbon: "E-STOP: all motion held. Release to continue." with a Release button. Not dismissible any other way.
- **SAFETY HOLD banner**: `hazard` striped bar naming the cause ("Person in view") and that motion resumes when it clears.
