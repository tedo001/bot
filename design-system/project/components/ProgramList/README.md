# ProgramList

A teach-pendant style program: numbered lines mixing taught motions, gripper and perception steps with natural-language steps the policy executes.

**Consumer provides:** `lines` (`op` + `text` + `kind`), `name`, `current` (the executing line while RUNNING), `selected` + `onSelect` for editing, `status`, and `palette` + `onInsert` to show the instruction tiles.

- Language lines (`kind: 'language'`) are set in the sans face so they read as sentences, not code.
- The executing line is `drive-soft` with a play marker; the view scrolls to keep it visible.
