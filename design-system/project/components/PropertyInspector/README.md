# PropertyInspector

Edits the selected cell item: location, appearance, visibility and collision, laid out as compact labelled fields.

**Consumer provides:** `title` and `icon` of the selection, `sections` of `fields` (`label`, `value`, `unit`, `kind`, `axis` for X/Y/Z colour ticks), `columns: 3` for coordinate triplets.

- Positions in millimetres, rotations in degrees, units inside the field.
- Fields under a locked safety config are disabled, with the reason in the section.
