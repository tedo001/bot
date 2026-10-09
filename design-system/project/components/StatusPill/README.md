# StatusPill

The controller's run status as a word, an icon and a tint: IDLE, LOADING, RUNNING, SUCCEEDED, STOPPED, SAFETY HOLD, FAILED.

**Consumer provides:** `status` exactly as `RunStatus` (`idle`, `loading`, `running`, `succeeded`, `stopped`, `safety_hold`, `failed`); `size` `lg` in the right dock header.

- Always visible: in the status bar on every screen and at the top of the Run panel.
- Never rename the states or show colour without the word.
- LOADING spins; nothing else animates.
