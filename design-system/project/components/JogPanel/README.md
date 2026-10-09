# JogPanel

The jog pendant: move the arm by hand, joint by joint or along a Cartesian frame, with a hold-to-run deadman and a capped speed override.

**Consumer provides:** `joints` and `cartesian` axes (defaults: the GP7's six joints and vendor limits), `onJog`, `onRecord`, `onHome`, and `disabledReason` whenever jogging is not allowed ("Jog is off while RUNNING", "Release E-STOP to jog").

- +/− keys are disabled until the deadman is held (`Space` or the hazard bar).
- Speed override is capped at 25% while jogging; the default is 10%.
- A joint within 5% of its limit turns `hold`.
- Show it docked in Program and floating (`Panel floating`) over the viewport elsewhere.
