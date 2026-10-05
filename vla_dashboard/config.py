"""Runtime configuration.

Every knob that trades latency against accuracy lives here, so the pipeline can be
tuned without touching code. Values can be overridden with environment variables
prefixed ``VLA_`` (e.g. ``VLA_BRAIN_BACKEND=openpi``), via pydantic-settings.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VLA_", extra="ignore")

    # ---- Simulator / control loop -------------------------------------------------
    frame_width: int = Field(640, ge=160, le=1920)
    frame_height: int = Field(480, ge=120, le=1080)
    control_hz: float = Field(20.0, gt=0, le=200)
    display_fps: float = Field(30.0, gt=0, le=120)  # GUI repaint cap; extra frames are dropped
    max_episode_steps: int = Field(600, ge=1)

    # ---- Simulator backend ----------------------------------------------------------
    # "pybullet": Yaskawa Motoman GP7/GP8 with vendor CAD meshes + rigid-body physics.
    # "kinematic": dependency-free numpy/OpenCV stand-in. "auto": pybullet if installed.
    sim_backend: Literal["auto", "pybullet", "kinematic"] = "auto"
    robot_model: Literal["gp7", "gp8"] = "gp7"
    sim_mesh_detail: Literal["fast", "full"] = "fast"  # "full" = original CAD meshes (use with EGL/GPU)
    sim_async_render: bool = True  # render in a separate process so control never waits on the renderer
    sim_use_egl: bool = False  # GPU rendering through PyBullet's EGL plugin (Linux + GPU driver)

    # ---- Perception ---------------------------------------------------------------
    # "auto" tries the real model and falls back to the mock if the package/weights are missing.
    perception_mode: Literal["auto", "mock", "real"] = "auto"
    rtdetr_checkpoint: str = "PekingU/rtdetr_r18vd"  # HF transformers, Apache-2.0
    rtdetr_threshold: float = Field(0.5, ge=0, le=1)
    det_stride: int = Field(1, ge=1)  # run RT-DETR every N frames
    rfdetr_threshold: float = Field(0.5, ge=0, le=1)
    seg_stride: int = Field(3, ge=1)  # run RF-DETR segmentation every N frames; masks reused in between
    ocr_interval_s: float = Field(5.0, gt=0)  # workspace labels are static: re-scan rarely
    safety_labels: tuple[str, ...] = ("person",)  # RT-DETR classes that trigger a safety hold

    # ---- VLA brain ----------------------------------------------------------------
    brain_backend: Literal["mock", "openvla", "openpi"] = "mock"
    openvla_url: str = "http://127.0.0.1:8000/act"  # openvla/vla-scripts/deploy.py
    openvla_unnorm_key: str = "bridge_orig"
    openpi_host: str = "127.0.0.1"  # openpi/scripts/serve_policy.py
    openpi_port: int = 8000
    action_horizon: int = Field(4, ge=1, le=64)  # actions executed per inference call
    # Start the next inference when this fraction of the current chunk is consumed (0 = off).
    # Hides model latency behind execution of the current chunk.
    prefetch_ratio: float = Field(0.5, ge=0, lt=1)
    inference_timeout_s: float = Field(2.0, gt=0)

    # ---- Safety -------------------------------------------------------------------
    max_translation_step: float = Field(0.02, gt=0)  # metres per control tick
    max_rotation_step: float = Field(0.15, gt=0)  # radians per control tick
    watchdog_s: float = Field(0.5, gt=0)  # hold position if no fresh command arrives in time
