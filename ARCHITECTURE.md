# Architecture

## 1. What the sibling repositories contribute

| Repo | What it is | What this app takes from it |
|---|---|---|
| `openvla` | 7B VLA (Prismatic + Llama-2). `vla-scripts/deploy.py` serves `POST /act` with `{image, instruction, unnorm_key}` and returns one 7-DoF action: EE delta + absolute gripper. | `OpenVLARestPolicy`: keep-alive HTTP session, 224² image, gripper absolute→delta conversion. One action per call, so latency matters most here. |
| `openpi` | π₀ / π₀-FAST flow/autoregressive VLAs. `openpi-client` speaks msgpack over a websocket. Policies return **action chunks** (H×D). `ActionChunkBroker` replays a chunk step by step. | `OpenPIWebsocketPolicy` (LIBERO obs keys `observation/image`, `observation/wrist_image`, `observation/state`, `prompt`; 7-D actions). The chunking idea is generalised into `ChunkScheduler` with async prefetch and delay compensation. |
| `home-robot` | Meta's mobile-manipulation stack, the base of OK-Robot. Abstract `Agent.act(obs) -> Action`, `ContinuousEndEffectorAction(pos, quat, g)`, Detic/Grounded-SAM perception wrappers. | The modular "perceive → ground → grasp → place" design of `OKRobotScriptedPolicy`, plus `to_home_robot_action()`, which adapts `ActionCommand` to `ContinuousEndEffectorAction` for real hardware. |
| `Awesome-Robotics-Manipulation` | Paper list. | Background only. |
| `sentra` | Unrelated (HSE incident-report analytics). | Nothing. |

## 2. Threads and data flow

```
┌──────────── GUI thread (PyQt6) ────────────┐
│ InstructionPayload ─► ControlWorker.submit │◄── frame_ready(np.ndarray)  ── zero-copy QImage → FrameView.paintEvent
│ console ◄── deque drained every 100 ms     │◄── state_ready(SystemState) ── 10 Hz telemetry
└────────────────────────────────────────────┘
          │ command queue (callables, run between ticks → sim has a single owner)
          ▼
┌──────── ControlWorker (QThread, fixed 20 Hz, deadline scheduled) ────────┐
│ sim.render() ─► FramePacket ─► frame_slot (LatestSlot) ──────────────────┼──► PerceptionWorker (QThread)
│ perception_slot.peek()  (non-blocking, newest result)  ◄─────────────────┼──── RT-DETR  every det_stride
│ VLABrain.step(make_obs) ─► ChunkScheduler ──► vla-infer thread (prefetch)│     RF-DETR  every seg_stride (+ skeleton)
│ RobotController.apply(ActionCommand) ─► sim.apply_delta                  │     PaddleOCR every ocr_interval_s (cached)
│ compose overlays (only at display_fps) ─► frame_ready                    │     ground OCR→objects, build SceneIndex
└──────────────────────────────────────────────────────────────────────────┘
```

## 3. Why it is fast

1. **Latest-wins hand-off (`LatestSlot`).** Producer and consumer stages never queue. A slow detector skips stale frames instead of building a backlog, so latency stays bounded at ≤ 1 producer period + 1 consumer run.
2. **No per-tick waiting on perception.** The control loop `peek()`s the newest perception result and keeps 20 Hz even if a real RF-DETR runs at 8 Hz.
3. **Stride scheduling.** Each model runs only as often as its output changes: OCR every few seconds (static labels), segmentation every 3rd frame (masks reused), RT-DETR every frame (safety).
4. **O(1) target retrieval (`SceneIndex`).** OCR text is grounded onto detections once per perception pass. Synonyms ("red", "block", "box" → `cube`) go into a dict, and each object's 3D position is lifted by ray-plane intersection. The brain resolves an instruction with dict lookups.
5. **Action chunking + async prefetch + delay compensation.** One inference → H actions. The next inference starts at `prefetch_ratio·H`, so it overlaps execution. Actions already executed since that observation are dropped, so the robot never replays motion.
6. **Lazy observations.** `make_obs` (image resize/encode) runs only on ticks that issue an inference.
7. **Zero-copy display.** Frames cross threads as Python references and `QImage` wraps the numpy buffer. Compositing happens off the GUI thread and only at display rate. The log console is bounded and batched.
8. **Model-side.** fp16 + `inference_mode` + warm-up for RT-DETR, `optimize_for_inference()` for RF-DETR, persistent HTTP/websocket connections for remote VLAs.

## 4. Why it is reliable

* Pydantic v2 at every boundary: `InstructionPayload` (length, control characters, needs words), `ActionCommand` (bounded and finite; `from_array` saturates overshoot but rejects NaN/inf), `Detection`/`BBox` (non-degenerate), `RobotState` (finite pose).
* `RobotController` is the only writer to the robot. It enforces E-STOP (operator-owned, survives episode resets), the RT-DETR safety hold (`person` in view), a watchdog hold, and per-tick rate limits tighter than the schema limits.
* Bounded inference wait (`inference_timeout_s`): a late model causes a hold, never a frozen loop.
* Every real model has a mock fallback (`perception_mode=auto`), so the app always starts. `real` makes missing models a hard error.
* Exceptions in perception or the control tick are logged and contained to that tick or episode. Threads keep running.

## 5. Measured latency (CPU, mock models, 640×480)

| Stage | Time |
|---|---|
| Simulator render (cached static layer) | ~0.8 ms |
| Mock perception pass (det + grounding) | ~0.3–0.6 ms |
| Full control tick incl. synchronous perception | ~1.6 ms (budget at 20 Hz: 50 ms) |

With real models, the budget is dominated by RF-DETR / RT-DETR GPU inference. They run on the perception thread, so they lower perception Hz, not control Hz.

## 6. Licences

PyQt6 (GPLv3 / commercial), Pydantic (MIT), OpenCV (Apache-2.0), HF transformers + RT-DETR weights (Apache-2.0), rfdetr (Apache-2.0), PaddleOCR (Apache-2.0), openpi (Apache-2.0), OpenVLA code (MIT; check the model weights' licence). **Ultralytics (AGPL-3.0) is not used anywhere.** Note that PyQt6 itself is GPLv3 unless you hold a commercial licence. Swap to PySide6 (LGPL) if that matters; the code uses no PyQt-only APIs except `pyqtSignal` (→ `Signal`).
