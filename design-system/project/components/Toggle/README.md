# Toggle

An on/off setting that applies immediately: overlays (boxes, masks, skeleton, OCR, HUD), visibility, collision detection.

**Consumer provides:** `label`, optional `hint` naming the source ("RF-DETR"), `checked` + `onChange` or `defaultChecked`.

- Use a toggle only when the change takes effect at once. Settings that need Apply (safety) use fields and the Apply button instead.
- Keep the label positive ("Show masks"), never a double negative.
