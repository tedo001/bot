# TrainingProgress

Trains a new policy without stopping the robot: pick a preset, start, and follow the three stages (teacher demonstrations, training epochs, closed-loop evaluation) to an automatic switch-in.

**Consumer provides:** `status`, `stage` (0–2), `progress` (0–1, from the trainer's `@@progress` lines), `message`, `preset` + `onPresetChange`, `onTrain`, `onStop`.

- Training runs in its own process: keep RunControls enabled while it runs.
- On success, show the new model in `ModelRegistry` as DRIVING and put an info `Banner` up while it loads.
