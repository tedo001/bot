# Icons

24px stroke icons, 1.75px stroke, round caps and joins, 2px padding on a 24 grid. The files are single-ink: drawn in `ink` light (#14181d), so as images they read only on light grounds. In the product use the bundle's `Icon` component (`h(VLAStudio.Icon, {name: 'play'})`), which draws the same paths with `currentColor` and so follows the text colour in both themes.

| Icon | Means |
|---|---|
| `play`, `pause`, `stop`, `step`, `reset` | Run controls: run, pause, stop, step one action chunk, reset scene |
| `home` | Go home pose |
| `estop` | E-STOP (octagon); only on the E-STOP control and banner, and on FAILED pills |
| `robot`, `gripper` | Robot / controller rows, gripper state |
| `jog`, `axes` | Jog pendant; frames (world, tool, user) |
| `cube`, `target` | Scene objects; grounding target (SRC/DST) and detections |
| `camera`, `eye`, `layers` | Cameras; overlay visibility; cell browser |
| `program`, `shield`, `policy`, `train` | Workspaces: Program, Safety, the policy (brain), Train |
| `chart`, `terminal`, `sliders` | Telemetry and diagnostics; console; settings |
| `warning`, `check`, `lock` | SAFETY HOLD and warnings; OK and SUCCEEDED; locked safety config |
| `chevron` | Expand and collapse in trees and panels (rotated 90° when open) |
