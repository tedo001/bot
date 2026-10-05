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
    ap.add_argument("--backend", choices=["learned", "mock", "openvla", "openpi"], help="VLA policy backend")
    ap.add_argument("--perception", choices=["auto", "mock", "real"], help="perception model mode")
    ap.add_argument("--hz", type=float, help="control loop rate")
    ap.add_argument("--sim", choices=["auto", "pybullet", "kinematic"], help="simulator backend")
    ap.add_argument("--robot", choices=["gp7", "gp8"], help="Yaskawa Motoman model (pybullet sim)")
    ap.add_argument("--egl", action="store_true", help="GPU rendering via EGL + full CAD meshes")
    args, _ = ap.parse_known_args(argv)
    overrides = {k: v for k, v in (("brain_backend", args.backend), ("perception_mode", args.perception),
                                   ("control_hz", args.hz), ("sim_backend", args.sim),
                                   ("robot_model", args.robot)) if v is not None}
    if args.egl:
        overrides.update(sim_use_egl=True, sim_mesh_detail="full")
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
