# Viewport

The centre of every screen: the 3D cell or the camera frame, with the view cube, axis triad, perception overlays and the policy's SRC/DST marks. Floating windows and banners sit on top of it.

**Consumer provides:** `mode` (`3d` or `camera`), `objects` from the scene index (with `mark` for the policy's choice), `overlays` flags from the overlay toggles, `hud` text (loop rate, latency), `tcp`, and children such as a floating `JogPanel`.

- In the product the scene is the simulator's render; this component's schematic stands in for it in designs. Scene colours are the simulator's render colours, not UI tokens.
- Only `viewport` ground, overlay marks and floating `surface-raised` windows belong here.
- Overlays keep their colours in both themes because they're drawn on imagery.
