"""Application entry point: ``python run.py`` or ``python -m vla_dashboard``."""

from __future__ import annotations

import argparse
import logging
import sys

from PyQt6.QtWidgets import QApplication

from .config import AppConfig
from .gui.main_window import MainWindow


def parse_args(argv: list[str] | None = None) -> AppConfig:
    ap = argparse.ArgumentParser(description="VLA robot dashboard + simulator")
    ap.add_argument("--backend", choices=["mock", "openvla", "openpi"], help="VLA policy backend")
    ap.add_argument("--perception", choices=["auto", "mock", "real"], help="perception model mode")
    ap.add_argument("--hz", type=float, help="control loop rate")
    args, _ = ap.parse_known_args(argv)
    overrides = {k: v for k, v in (("brain_backend", args.backend), ("perception_mode", args.perception),
                                   ("control_hz", args.hz)) if v is not None}
    return AppConfig(**overrides)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = parse_args(argv)
    app = QApplication(sys.argv)
    app.setApplicationName("VLA Robot Dashboard")
    app.setStyle("Fusion")
    win = MainWindow(cfg)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
