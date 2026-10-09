# EStop

The latching emergency stop. Pressing it, or `Esc`, zeroes every robot command; it stays engaged through episode ends and scene resets until the operator releases it.

**Consumer provides:** `engaged` + `onChange` wired to `RobotController.estop` (or `defaultEngaged`), `compact` for the 48px ribbon version. Only one EStop per page owns `Esc`; set `hotkey={false}` on any other.

- Always visible at the right end of the ribbon on every screen. Never disabled, never covered.
- It is the only control filled with `estop`. When engaged, also show the E-STOP `Banner`.
- Releasing never resumes motion by itself: a held episode becomes STOPPED.
