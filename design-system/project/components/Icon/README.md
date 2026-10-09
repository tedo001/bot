# Icon

Draws one of the 27 studio icons as a 24-grid stroke SVG in `currentColor`, so it follows the text colour in both themes.

**Consumer provides:** `name` (see `ICON_NAMES`), optional `size` in px (16 in dense UI, 20 in the ribbon, 14 inside pills and trees) and `label` when the icon stands alone and means something.

- Do pair icons with words. An icon-only button needs `aria-label` and a tooltip.
- Do use `estop` only for E-STOP and FAILED, `warning` only for SAFETY HOLD and warnings, `check` only for OK and SUCCEEDED.
- Don't recolour icons with signal colours for decoration; they take the colour of the state they sit in.
