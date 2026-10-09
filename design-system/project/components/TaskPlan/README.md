# TaskPlan

Shows what the policy decided before and while it moves: the SOURCE and DESTINATION objects, the done probability, and the episode's phases with the current one highlighted.

**Consumer provides:** `phases`, `current` index, `status` (`running`, `hold`, `done`, `failed`), `source` and `destination` names (the same objects marked in the viewport), `doneProb` from the policy, and `message` for a failure reason.

- Show it as soon as an instruction is previewed, not only while running.
- The SRC and DST tags use the same `mark-src` and `mark-dst` as the viewport, so the operator can match them at a glance.
