# Banner

A full-width bar for a condition that stops or holds the robot: E-STOP engaged, SAFETY HOLD with its cause, or an info notice such as a model being switched in.

**Consumer provides:** `kind` (`estop`, `hold`, `info`), a short `title`, a `message` naming the cause and what happens next, and an `action` when the operator can resolve it ("Release").

- Place it directly under the ribbon (or along the viewport's bottom edge) at `z-banner`. It is never dismissible while the condition holds.
- Show it instantly, without animation.
