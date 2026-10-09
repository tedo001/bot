"""Rebuild project/components/bundle.js from bundle.src.js and the icon paths (run icons.py first if icons changed)."""
import json
from pathlib import Path

HERE = Path(__file__).parent
NAMES = ["Icon", "Button", "Segmented", "Toggle", "RunControls", "StatusPill", "EStop", "Banner", "SafetyChecks",
         "InstructionBox", "TaskPlan", "ProgramList", "JogPanel", "PoseReadout", "CellTree", "PropertyInspector",
         "Viewport", "Telemetry", "Console", "TrainingProgress", "ModelRegistry", "Ribbon", "Panel", "StatusBar"]

src = (HERE / "bundle.src.js").read_text()
icons = json.loads((HERE / "icons.json").read_text())
header = "/* @ds-bundle: " + json.dumps({"format": 4, "namespace": "VLAStudio", "components": [{"name": n} for n in NAMES]},
                                         separators=(",", ":")) + " */\n"
out = header + src.replace("__ICONS__", json.dumps(icons, separators=(",", ":")))
assert "</script" not in out.lower() and "<!--" not in out, "bundle must be inlinable"
(HERE / "project/components/bundle.js").write_text(out)
print(f"bundle.js: {len(out)} bytes")
