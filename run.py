"""PyCharm entry point: right-click -> Run 'run'.

Checks the environment before starting and prints the exact fix for the usual setup
errors: Python too old, run.py copied without the vla_dashboard folder, packages missing
from the interpreter PyCharm uses, and the system library Qt needs on Ubuntu.
"""

import ctypes.util
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = "git clone -b sim https://github.com/tedo001/bot.git"
REQUIRED = {"PyQt6": "PyQt6", "pydantic": "pydantic", "pydantic_settings": "pydantic-settings", "numpy": "numpy",
            "cv2": "opencv-python-headless"}
OPTIONAL = {"pybullet": "the Yaskawa GP7 simulator (falls back to the simple simulator)",
            "torch": "the learned policy (falls back to the rule-based planner)"}


def _fail(msg: str) -> None:
    print(f"\n[run.py] ERROR: {msg}\n", file=sys.stderr)
    sys.exit(1)


def _warn(msg: str) -> None:
    print(f"[run.py] warning: {msg}", file=sys.stderr)


def preflight() -> None:
    if sys.version_info < (3, 10):
        _fail(f"Python 3.10 or newer is required, but PyCharm is using {sys.version.split()[0]} "
              f"({sys.executable}).\n  Fix: Settings > Project > Python Interpreter > pick a 3.10+ interpreter.")
    if not (ROOT / "vla_dashboard" / "__init__.py").is_file():
        _fail(f"the 'vla_dashboard' folder must sit next to run.py (looked in {ROOT}).\n"
              f"  Fix: get the whole project, not just run.py:\n    {REPO}\n"
              "  then in PyCharm: File > Open > the 'bot' folder, and run run.py from there.")
    sys.path.insert(0, str(ROOT))  # works whatever PyCharm's working directory / content roots are

    missing = [pip for mod, pip in REQUIRED.items() if importlib.util.find_spec(mod) is None]
    if missing:
        _fail(f"missing package(s) in the interpreter PyCharm uses ({sys.executable}): {', '.join(missing)}\n"
              "  Fix (run in PyCharm's Terminal):\n"
              f"    \"{sys.executable}\" -m pip install -r \"{ROOT / 'requirements.txt'}\"")
    for mod, what in OPTIONAL.items():
        if importlib.util.find_spec(mod) is not None:
            continue
        if mod == "pybullet" and sys.platform == "win32":
            _warn("'pybullet' is not installed, so the Yaskawa GP7 simulator is off (using the simple simulator).\n"
                  "  PyPI has no Windows build of pybullet, so it must be compiled once:\n"
                  "    1. install 'Microsoft C++ Build Tools' (workload: Desktop development with C++)\n"
                  "       https://visualstudio.microsoft.com/visual-cpp-build-tools/\n"
                  "    2. in PyCharm's Terminal (venv active):  pip install pybullet\n"
                  "  or, with conda:  conda install -c conda-forge pybullet")
        else:
            _warn(f"'{mod}' is not installed: {what}. Install with: pip install -r requirements.txt")

    if sys.platform.startswith("linux") and os.environ.get("QT_QPA_PLATFORM", "") not in ("offscreen", "minimal"):
        if ctypes.util.find_library("xcb-cursor") is None and os.environ.get("XDG_SESSION_TYPE") != "wayland":
            _warn("libxcb-cursor0 not found; Qt 6.5+ needs it to open a window on X11.\n"
                  "  If you see 'Could not load the Qt platform plugin \"xcb\"', run:\n"
                  "    sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1")


if __name__ == "__main__":
    preflight()
    from vla_dashboard.app import main

    sys.exit(main())
