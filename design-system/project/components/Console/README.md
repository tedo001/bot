# Console

The log stream from every thread, filtered by level. Errors carry the fix text the rest of the UI shows.

**Consumer provides:** `lines` (`t` time, `level`, `src` logger, `msg`), `filter` + `onFilterChange`, `height`.

- Bound it (the app keeps 3,000 lines) and append in batches; never one repaint per line.
- WARN lines use `hold`, ERROR lines `danger` on `danger-soft`; INFO stays ink.
