# SafetyChecks

The list of every safety check the controller enforces, each with its limit and a state: OK, CHANGED (edited, not yet applied) or FAULT.

**Consumer provides:** `checks` (`name`, `detail`, `value`, `state`), and `selected` + `onSelect` when a settings form edits the selected row.

- Any CHANGED or FAULT row blocks Run; pass that reason to `RunControls`.
- Values are the real configured limits with units (`watchdog_s` 0.50 s, `inference_timeout_s` 2.00 s).
- States carry a word and an icon as well as colour.
