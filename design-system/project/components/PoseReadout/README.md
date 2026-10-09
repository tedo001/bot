# PoseReadout

The TCP pose (X Y Z, W P R) and gripper state as live mono readouts.

**Consumer provides:** `pose` (metres and degrees from `RobotState`), `gripper` (`opening` 0–1, `holding` object name), `frame` name, `linearUnit` (`m` in telemetry, `mm` in the Program workspace), and `stale` with the data's age when it stops updating.

- Values are signed and fixed-width so they don't jitter at 10 Hz.
- Stale data goes muted with its age; never freeze a value silently.
