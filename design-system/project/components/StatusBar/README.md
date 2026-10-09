# StatusBar

The bottom line of every screen: run status, controller, program, what is driving the arm, loop rate, speed override, safety checksum.

**Consumer provides:** `status` and `items` (`label`, `value`, `icon`, `tone`, `push` to start the right-aligned group).

- The driving item is `ok` for a trained model and `danger` if the brain ever falls back to rules, as in the app.
- Keep values short and mono; details live in panels.
