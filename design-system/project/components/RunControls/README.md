# RunControls

Run, Step, Pause, Stop and Reset for one episode, with each button enabled exactly as the run-state table in System flow says.

**Consumer provides:** the current `status` (a `RunStatus`), handlers `onRun`, `onStep`, `onPause`, `onStop`, `onReset`, and `disabledReason` when something outside the run state blocks running (a CHANGED safety row, models loading).

- Keep it in the right dock under the instruction; never split the buttons apart.
- E-STOP is not part of this group: it lives in the ribbon and is never disabled.
- `Ctrl+Enter` runs and `F5` steps from anywhere in the window.
