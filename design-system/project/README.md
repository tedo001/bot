VLA Robot Studio is the operator interface for a simulated industrial arm (Yaskawa Motoman GP7/GP8 on MuJoCo or PyBullet) driven by a language-conditioned policy. It is engineering software in the ROBOGUIDE / RoboDK family: a ribbon, docked panels around a 3D cell, a floating jog pendant, and a safety layer that is always one keystroke away. The UI has to be calm while things are fine, and impossible to misread when they are not.

## Principles

1. **Safety is never more than one action away.** The E-STOP button sits at the right end of the ribbon on every screen, `Esc` toggles it, and its state survives resets. Nothing may cover it (`z-banner` is reserved for the E-STOP and SAFETY HOLD banners).
2. **The robot's state is always visible.** Every screen shows the run status (`StatusPill`), what is driving the arm (trained model or rule fallback) and the loop rate in the `StatusBar`.
3. **Show what the robot is about to do before it does it.** The policy's SOURCE and DESTINATION choices are drawn in the viewport (`mark-src`, `mark-dst`) and listed in the `TaskPlan` before and during motion.
4. **Numbers are instruments.** Live values are set in mono (`readout`), aligned, signed (`+0.412`), and never shown without a unit.
5. **Colour carries meaning, never decoration.** Signal colours (`estop`, `danger`, `hold`, `ok`, `busy`) appear only for the state they name, always with a word and an icon beside them.

## Content fundamentals

- **Voice:** an experienced cell technician talking to an operator. Short, imperative, specific. "Release E-STOP to move the arm", not "Oops! Something went wrong".
- **Person:** address the operator as *you* only in help text; buttons and menu items are verbs ("Run simulation", "Train new model", "Reset scene", "Go home").
- **Casing:** sentence case for buttons, labels and menus. Panel titles (`panel-title`) and run-status words (`status`) are capitals: `CELL BROWSER`, `RUNNING`, `SAFETY HOLD`. Model and file names keep their own case: `vla_act.pt`, `GP7`, `RT-DETR`.
- **Statuses** are the controller's words, exactly: IDLE, LOADING, RUNNING, SUCCEEDED, STOPPED, SAFETY HOLD, FAILED. Do not invent synonyms ("Done!", "Error").
- **Errors** say what happened, why, and the fix, in that order: "Episode failed: no object matches 'banana'. Name an object in the scene, e.g. 'the red cube'."
- **Units:** metres for poses in telemetry (`m`, three decimals), millimetres in the property inspector and jog (`mm`, one decimal), degrees for joints and WPR (`deg`), `Hz` for rates, `ms` for latency, `%` for speed override.
- **No emoji, no exclamation marks.** Glyphs come from the icon set only.
- Real copy from the app to reuse: "Put the red cube on the blue cylinder", "Pick up the green ball", "Place the sphere next to the cube", "Go home"; "E-STOP (hold all motion)"; "Driving: trained model vla_act.pt".

## Visual foundations

### Colour

- Two themes: **Light (office)** for programming and review, **Dark (cell floor)** for running next to hardware or on a control-room screen. Both are first-class; every token has both values.
- Grounds stack `surface` → `surface-raised` (panels) → `surface-sunken` (wells inside panels). The 3D cell and camera frame sit on `viewport`; only overlay marks and floating `surface-raised` windows go on it.
- `drive` is the one action colour: the Run button, selection, the active tab, links. One `drive`-filled button per region at most; label it with `on-drive`.
- `estop` fills only the E-STOP control and banner; labels on it are `on-estop`. Ordinary errors use `danger`, never `estop`.
- Status pairs: text in the signal colour on its `-soft` ground (`ok` on `ok-soft`, `hold` on `hold-soft`, `danger` on `danger-soft`, `busy` on `busy-soft`, `drive` on `drive-soft` for RUNNING). Every pair is 4.5:1 or better in both themes.
- `ok` and `danger` are close in lightness, so a status never relies on colour: the pill always has its word and icon (check, octagon-stop, triangle, spinner).
- `hazard` (safety yellow) with `on-hazard` stripes marks a SAFETY HOLD banner and the jog deadman bar, nothing else.
- Overlay marks (`mark-*`) and axis colours (`axis-x/y/z`) have the same value in both themes because they are drawn on rendered imagery. Axes are always labelled X, Y, Z.

### Type

- **IBM Plex Sans** for UI text, **IBM Plex Sans Condensed** for titles and status words, **IBM Plex Mono** for every live number, console line and program line (Google Fonts; `components/bundle.css` imports all three).
- Ten styles only: `screen-title`, `panel-title`, `status`, `body`, `body-strong`, `label`, `caption`, `readout`, `readout-lg`, `code`. Dense panels use `label` and `readout`; `body` is for instructions and help.
- Numbers use tabular figures (`font-variant-numeric: tabular-nums`) so columns don't jitter at 10 Hz.

### Space, size, shape

- 4px grid: `space-1` … `space-6` (4, 8, 12, 16, 24, 32). Panel bodies pad `space-3`; rows gap `space-2`.
- Control heights: `control-sm` (24) in trees and toggles, `control-md` (32) default, `control-lg` (40) for run controls. The E-STOP is `estop-size` (64) and round.
- Corners are tight and industrial: `radius-sm` on controls, `radius-md` on panels and floating windows, `radius-xs` on tags, `radius-full` only for pills, toggle tracks and the E-STOP.
- **Borders, not shadows.** Docked panels are separated by `line` hairlines. Only floating windows over the viewport get `shadow-float`; only the E-STOP gets `shadow-estop`.
- Control borders use `line-strong` (3:1 on every ground). `line` is decorative only.

### Layout

The studio is a dock layout at 1280 × 800 and up:

| Region | Size | Holds |
|---|---|---|
| Ribbon | `ribbon-height` | workspace tabs (Workcell, Program, Run, Safety, Train, Diagnostics), the active workspace's tool groups, E-STOP at the far right |
| Left dock | `dock-width` | Cell browser (scene tree), Property inspector |
| Centre | flexible | Viewport: 3D cell or camera, view cube, axis triad, overlays, floating jog pendant |
| Right dock | `dock-width` | Instruction, run controls, task plan, telemetry (varies by workspace) |
| Bottom | 160–240px, collapsible | Console, episodes |
| Status bar | `statusbar-height` | controller, program, run status, driving brain, loop Hz, speed override, messages |

Docks collapse to icon rails below 1280px; the viewport, the status pill and the E-STOP never collapse.

### States and motion

- Hover: `surface-sunken` ground on quiet controls, `drive-soft` on drive controls. Pressed: 1px inset. Disabled: 40% opacity plus `not-allowed`; a disabled Run button says why in its tooltip ("Models still loading").
- Focus: `focus-ring`, a solid 2px ring with a 2px gap in the ground colour, on every focusable control. Never remove it.
- Motion is functional only: 120ms ease-out for hovers and panel collapse, a 1s linear spinner for LOADING. The E-STOP banner appears instantly, never animated in.

### Interaction rules

- `Ctrl+Enter` runs the instruction, `Esc` toggles E-STOP, `Space` (held) is the jog deadman, `F5` steps one action chunk in Step mode, `Home` sends the arm home (with confirmation while RUNNING).
- Jogging needs the deadman held and speed override ≤ 25% by default; the jog pendant disables while RUNNING.
- Changing a safety setting puts its row in CHANGED (`hold`) until it is applied and verified; the arm cannot run with a CHANGED row.
- Destructive actions (delete a trained model, reset safety config) ask for confirmation in a dialog that names the object.

## Iconography

- One set of 24px stroke icons, 1.75px stroke, round caps and joins, drawn on a 24 grid with 2px padding: `assets/Icons/`. In code use `Icon name="…"`, which draws with `currentColor`.
- Icons accompany words; an icon-only button needs a tooltip and `aria-label`.
- The set: play, pause, stop, step, reset, home, estop, robot, gripper, jog, axes, cube, target, camera, eye, layers, program, shield, policy, train, chart, terminal, sliders, warning, check, lock, chevron.
- There is no logo yet. Set the product name as text in `screen-title`; do not draw a mark.

## Components

The bundle exposes React components on `window.VLAStudio`; previews show each one. Build screens from them in this order of precedence: shell (`Ribbon`, `Panel`, `StatusBar`), safety (`EStop`, `SafetyChecks`), state (`StatusPill`, `TaskPlan`), then tools. The **System flow** and **Screens** sections below describe how the screens connect and what each one must contain.
