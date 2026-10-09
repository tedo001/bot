# Panel

A docked panel: a capitalised title bar with optional icon, meta and actions, and a padded body. `floating` lifts it over the viewport with `shadow-float`.

**Consumer provides:** `title` (shown in capitals), `icon`, `meta` (a count or rate), `actions` (quiet icon buttons), `collapsible`, `flush` for edge-to-edge content (trees, consoles), `footer`, `children`.

- Docked panels are separated by hairlines, never shadows.
- Only floating windows over the viewport use `floating`.
