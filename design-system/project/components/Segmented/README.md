# Segmented

Picks one of two to five mutually exclusive modes that change what a panel shows: jog frame, step size, console filter, training preset.

**Consumer provides:** `options` (strings or `{value, label, icon}`), `value` + `onChange` (or `defaultValue`), a `label` for assistive tech, `size` `sm` inside dense panels.

- Use it for modes, not for actions. For more than five options use a select.
- The selected option is outlined in `drive`, so it does not rely on fill alone.
