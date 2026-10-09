# ModelRegistry

Every trained checkpoint with its closed-loop success rates, so the operator chooses what drives the arm on evidence.

**Consumer provides:** `models` (`name`, `file`, `trained` date, `sim`, `pybullet`, `mujoco` success 0–1 from the metrics sidecar, `driving`), `selected` + `onSelect`, `onActivate` to switch the brain.

- Exactly one row is DRIVING. It matches the status bar's driving line.
- Missing scores show an em dash, never 0%.
