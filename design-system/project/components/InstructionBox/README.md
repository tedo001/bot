# InstructionBox

Where the operator writes what the robot should do, in plain English. Validates with the same rules as the app's `InstructionPayload` and runs on `Ctrl+Enter`.

**Consumer provides:** `value` + `onChange` (or `defaultValue`), `onRun(text)`, and `examples` (the app's: "Put the red cube on the blue cylinder", "Pick up the green ball", "Place the sphere next to the cube", "Grab the blue can", "Go home").

- Errors explain the fix, never just "Invalid".
- Keep it at the top of the right dock in Workcell and Run.
