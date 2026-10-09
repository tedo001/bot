# Telemetry

Live numbers about the control loop: rate, perception latency, done probability, and the control tick's stage timings against its 50 ms budget at 20 Hz.

**Consumer provides:** `metrics` (`label`, `value`, `unit`, `note`, `tone` `hold` when off target), `stages` (ms per stage from `SystemState.stage_ms`), `budgetMs` (1000 / `control_hz`).

- Loop rate and perception latency are separate tiles: the loop never waits on perception, and the UI must not suggest it does.
- A tile goes `hold` with a note when it misses its target ("target 20 Hz").
