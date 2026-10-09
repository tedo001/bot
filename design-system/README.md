# VLA Robot Studio design system

Source of the published design system (tokens, brand book, system flow, screens, 24 React components, Workcell and SystemFlow pages, icons) for the dashboard's UI.

- `project/` is the design system exactly as published: start at `project/README.md`, then `project/FLOW.md` and `project/SCREENS.md`.
- `bundle.src.js` is the component source; `python build_bundle.py` writes `project/components/bundle.js`.
- `icons.py` holds the icon paths and writes `project/assets/Icons/*.svg` and `icons.json`.
