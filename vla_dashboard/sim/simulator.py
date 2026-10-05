"""Lightweight kinematic tabletop simulator (numpy + OpenCV, no physics engine).

Recreates the reference scene: a blue 6-axis arm behind a framed table carrying a red
cube, a blue cylinder and a green sphere, each with a printed text label that the OCR
stage can read. Rendering is ~1-2 ms per 640x480 frame because everything static
(background, table, labels) is drawn once and cached; each frame only copies that
cached layer and draws the objects and the arm on top.

World frame: x to the right, y away from the camera, z up. Units are metres.
Swap this class for a PyBullet/MuJoCo/Isaac backend by keeping the same public
methods: ``reset``, ``apply_delta``, ``render``, ``state``, ``camera``.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from ..frame_bus import FramePacket

# Colours are RGB because frames are RGB end to end (QImage.Format.Format_RGB888).
YASKAWA_BLUE = (28, 78, 205)
TABLE_X = (-0.40, 0.40)
TABLE_Y = (0.28, 0.92)
WORKSPACE_Z = (0.012, 0.40)
GRIPPER_RATE = 0.25  # opening change per tick for a gripper delta of 1.0
GRASP_RADIUS = 0.04


class PinholeCamera:
    """Fixed perspective camera. ``project`` maps world -> pixels; ``deproject_to_plane``
    casts a pixel ray back onto a horizontal plane, which is how 2D detections become
    3D grasp targets without a depth sensor."""

    def __init__(self, width: int, height: int, eye=(0.0, -0.50, 0.95), target=(0.05, 0.66, 0.16), fov_deg=58.0):
        self.width, self.height = width, height
        self.eye = np.asarray(eye, dtype=np.float64)
        fwd = np.asarray(target, dtype=np.float64) - self.eye
        fwd /= np.linalg.norm(fwd)
        right = np.cross(fwd, [0.0, 0.0, 1.0])
        right /= np.linalg.norm(right)
        down = np.cross(fwd, right)
        self.R = np.stack([right, down, fwd])  # rows: camera x, y, z axes in world
        self.f = 0.5 * width / math.tan(math.radians(fov_deg) / 2.0)
        self.cx, self.cy = width / 2.0, height / 2.0

    def project(self, pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(N, 3) world points -> (N, 2) pixels and (N,) depths."""
        pc = (np.atleast_2d(pts) - self.eye) @ self.R.T
        z = np.maximum(pc[:, 2], 1e-6)
        uv = np.empty((pc.shape[0], 2))
        uv[:, 0] = self.f * pc[:, 0] / z + self.cx
        uv[:, 1] = self.f * pc[:, 1] / z + self.cy
        return uv, z

    def deproject_to_plane(self, u: float, v: float, plane_z: float) -> tuple[float, float, float]:
        d = self.R.T @ np.array([(u - self.cx) / self.f, (v - self.cy) / self.f, 1.0])
        if abs(d[2]) < 1e-9:
            return float(self.eye[0]), float(self.eye[1]), plane_z
        t = (plane_z - self.eye[2]) / d[2]
        p = self.eye + t * d
        return float(p[0]), float(p[1]), float(plane_z)


@dataclass
class SimObject:
    name: str
    kind: str  # "cube" | "cylinder" | "sphere"
    color: tuple[int, int, int]
    size: float  # edge length or diameter
    height: float
    pos: np.ndarray  # centre, world frame
    instance_id: int = 0


@dataclass
class ArmState:
    ee: np.ndarray = field(default_factory=lambda: np.array([0.10, 0.60, 0.25]))
    rpy: np.ndarray = field(default_factory=lambda: np.zeros(3))
    gripper: float = 1.0  # 1 open, 0 closed
    holding: SimObject | None = None


class TabletopSim:
    BASE = np.array([0.30, 0.98, 0.0])
    SHOULDER_H, L1, L2, WRIST_OFFSET = 0.26, 0.42, 0.40, 0.11

    def __init__(self, width: int = 640, height: int = 480) -> None:
        self.camera = PinholeCamera(width, height)
        self.width, self.height = width, height
        self.frame_id = 0
        self.arm = ArmState()
        self.objects: list[SimObject] = []
        self._labels: list[tuple[str, tuple[float, float, float, float]]] = []
        self._static_rgb: np.ndarray | None = None
        self.reset()

    # ------------------------------------------------------------------ lifecycle
    DEFAULT_LAYOUT = {"cube": (-0.22, 0.46), "cylinder": (-0.05, 0.46), "sphere": (0.12, 0.46)}

    def reset(self, layout: dict[str, tuple[float, float]] | None = None, render_static: bool = True) -> None:
        """``layout`` maps object name -> (x, y) on the table (training / evaluation randomisation)."""
        xy = {**self.DEFAULT_LAYOUT, **(layout or {})}
        self.arm = ArmState()
        self.objects = [
            SimObject("cube", "cube", (220, 30, 30), 0.05, 0.05, np.array([*xy["cube"], 0.025]), 1),
            SimObject("cylinder", "cylinder", (35, 45, 215), 0.05, 0.06, np.array([*xy["cylinder"], 0.03]), 2),
            SimObject("sphere", "sphere", (40, 200, 70), 0.05, 0.05, np.array([*xy["sphere"], 0.025]), 3),
        ]
        if render_static:  # skipped when generating training data without images
            self._static_rgb = self._render_static()

    # ------------------------------------------------------------------ dynamics
    def apply_delta(self, d: np.ndarray) -> None:
        """Integrate one 7-D delta (dx, dy, dz, droll, dpitch, dyaw, dgripper)."""
        a = self.arm
        a.ee = a.ee + d[:3]
        a.ee[0] = np.clip(a.ee[0], *TABLE_X)
        a.ee[1] = np.clip(a.ee[1], *TABLE_Y)
        a.ee[2] = np.clip(a.ee[2], *WORKSPACE_Z)
        a.rpy = (a.rpy + d[3:6] + math.pi) % (2 * math.pi) - math.pi
        a.gripper = float(np.clip(a.gripper + GRIPPER_RATE * d[6], 0.0, 1.0))

        if a.holding is None and a.gripper < 0.4:
            obj = self._nearest(a.ee, GRASP_RADIUS)
            if obj is not None:
                a.holding = obj
        if a.holding is not None:
            a.gripper = max(a.gripper, 0.3)  # fingers stop at the object
            if a.gripper > 0.6:
                self._release(a.holding)
                a.holding = None
            else:
                a.holding.pos = a.ee.copy()

    def _nearest(self, p: np.ndarray, radius: float) -> SimObject | None:
        best, best_d = None, radius
        for o in self.objects:
            dist = float(np.linalg.norm(o.pos - p))
            if dist < best_d:
                best, best_d = o, dist
        return best

    def _release(self, obj: SimObject) -> None:
        """Drop straight down; stack on another object if its footprint is underneath."""
        z = obj.height / 2.0
        for o in self.objects:
            if o is obj:
                continue
            if np.linalg.norm(o.pos[:2] - obj.pos[:2]) < 0.6 * o.size:
                z = max(z, o.pos[2] + o.height / 2.0 + obj.height / 2.0)
        obj.pos = np.array([obj.pos[0], obj.pos[1], z])

    def state(self) -> dict:
        a = self.arm
        return {
            "ee": a.ee.copy(),
            "rpy": a.rpy.copy(),
            "gripper": a.gripper,
            "holding": a.holding.name if a.holding else None,
            "objects": {o.name: o.pos.copy() for o in self.objects},
        }

    # ------------------------------------------------------------------ kinematics
    def arm_joints(self) -> np.ndarray:
        """Elbow-up 2-link IK in the vertical plane through the shoulder and wrist.
        Returns world positions of [base, shoulder, elbow, wrist, tool]."""
        ee = self.arm.ee
        base = self.BASE
        shoulder = base + np.array([0.0, 0.0, self.SHOULDER_H])
        wrist = ee + np.array([0.0, 0.0, self.WRIST_OFFSET])
        v = wrist - shoulder
        horiz = np.array([v[0], v[1], 0.0])
        hn = np.linalg.norm(horiz)
        h_dir = horiz / hn if hn > 1e-6 else np.array([0.0, -1.0, 0.0])
        d = min(np.linalg.norm(v), self.L1 + self.L2 - 1e-3)
        elev = math.atan2(v[2], hn)
        cos_a = (self.L1**2 + d**2 - self.L2**2) / (2 * self.L1 * d)
        a = math.acos(float(np.clip(cos_a, -1.0, 1.0)))
        elbow = shoulder + self.L1 * (math.cos(elev + a) * h_dir + np.array([0.0, 0.0, math.sin(elev + a)]))
        return np.stack([base, shoulder, elbow, wrist, ee])

    # ------------------------------------------------------------------ rendering
    def _render_static(self) -> np.ndarray:
        h, w = self.height, self.width
        grad = np.linspace(225, 175, h, dtype=np.float32)[:, None]
        img = np.repeat(np.repeat(grad, w, axis=1)[:, :, None], 3, axis=2).astype(np.uint8)
        cam = self.camera

        corners = np.array([[TABLE_X[0], TABLE_Y[0], 0], [TABLE_X[1], TABLE_Y[0], 0],
                            [TABLE_X[1], TABLE_Y[1], 0], [TABLE_X[0], TABLE_Y[1], 0]], dtype=np.float64)
        uv, _ = cam.project(corners)
        poly = uv.astype(np.int32)
        cv2.fillConvexPoly(img, poly, (128, 128, 132), lineType=cv2.LINE_AA)
        # Aluminium frame rails + corner posts.
        top = corners + np.array([0, 0, 0.05])
        uv_top, _ = cam.project(top)
        for i in range(4):
            p0, p1 = uv_top[i].astype(int), uv_top[(i + 1) % 4].astype(int)
            cv2.line(img, tuple(p0), tuple(p1), (215, 218, 222), 5, cv2.LINE_AA)
            cv2.line(img, tuple(p0), tuple(p1), (160, 164, 170), 1, cv2.LINE_AA)
            cv2.line(img, tuple(poly[i]), tuple(p0), (200, 203, 208), 4, cv2.LINE_AA)
            cv2.circle(img, tuple(p0), 5, (25, 25, 25), -1, cv2.LINE_AA)

        # Printed workspace labels (what PaddleOCR is expected to read).
        self._labels = []
        font, scale, thick = cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
        for o in self.objects:
            text = o.name.upper()
            uv_l, _ = cam.project(np.array([o.pos[0], o.pos[1] - 0.075, 0.0]))
            u, v = uv_l[0]
            (tw, th), base = cv2.getTextSize(text, font, scale, thick)
            x0, y0 = int(u - tw / 2), int(v + th / 2)
            cv2.rectangle(img, (x0 - 4, y0 - th - 4), (x0 + tw + 4, y0 + base + 2), (240, 240, 235), -1)
            cv2.putText(img, text, (x0, y0), font, scale, (20, 20, 20), thick, cv2.LINE_AA)
            self._labels.append((text, (x0 - 4.0, y0 - th - 4.0, x0 + tw + 4.0, y0 + base + 2.0)))
        return img

    @staticmethod
    def _shade(c, k):
        return tuple(int(min(255, max(0, ch * k))) for ch in c)

    def _object_geometry(self, o: SimObject):
        """Projected silhouette (convex polygon or circle) plus the shaded faces to draw."""
        cam = self.camera
        if o.kind == "sphere":
            uv, z = cam.project(o.pos[None])
            u, v = uv[0]
            r = cam.f * (o.size / 2.0) / z[0]
            return ("circle", (u, v, r)), None
        if o.kind == "cube":
            s = o.size / 2.0
            offs = np.array([[x, y, zz] for zz in (-s, s) for y in (-s, s) for x in (-s, s)])
            uv, _ = cam.project(o.pos + offs)
            faces = []
            # (vertex indices, outward normal, brightness)
            for idx, n, k in (([4, 5, 7, 6], (0, 0, 1), 1.15), ([0, 1, 5, 4], (0, -1, 0), 0.85),
                              ([0, 2, 6, 4], (-1, 0, 0), 0.65), ([1, 3, 7, 5], (1, 0, 0), 0.65)):
                fc = o.pos + np.mean(offs[idx], axis=0)
                if np.dot(np.asarray(n, float), cam.eye - fc) > 0:
                    faces.append((uv[idx].astype(np.int32), self._shade(o.color, k)))
            hull = cv2.convexHull(uv.astype(np.float32)).astype(np.int32)
            return ("poly", hull), faces
        # cylinder
        th = np.linspace(0, 2 * np.pi, 28, endpoint=False)
        r, hh = o.size / 2.0, o.height / 2.0
        ring = np.stack([r * np.cos(th), r * np.sin(th), np.zeros_like(th)], axis=1)
        top_uv, _ = cam.project(o.pos + ring + [0, 0, hh])
        bot_uv, _ = cam.project(o.pos + ring - [0, 0, hh])
        hull = cv2.convexHull(np.vstack([top_uv, bot_uv]).astype(np.float32)).astype(np.int32)
        faces = [(hull, self._shade(o.color, 0.8)), (top_uv.astype(np.int32), self._shade(o.color, 1.15))]
        return ("poly", hull), faces

    def render(self) -> FramePacket:
        """Render one RGB frame plus an instance-id mask (ground truth for mock perception).

        The returned ``rgb`` array is freshly allocated and never written again, so it
        can be shared by reference across threads (GUI, perception, VLA) with no copies.
        """
        self.frame_id += 1
        img = self._static_rgb.copy()
        ids = np.zeros((self.height, self.width), dtype=np.uint8)
        cam = self.camera

        # Painter's algorithm: far objects first.
        order = sorted(self.objects, key=lambda o: -cam.project(o.pos[None])[1][0])
        for o in order:
            (kind, geo), faces = self._object_geometry(o)
            if kind == "circle":
                u, v, r = geo
                c = (int(round(u)), int(round(v)))
                cv2.circle(img, c, int(round(r)), o.color, -1, cv2.LINE_AA)
                cv2.circle(img, (int(u - r / 3), int(v - r / 3)), max(1, int(r / 3)), self._shade(o.color, 1.4), -1,
                           cv2.LINE_AA)
                cv2.circle(ids, c, int(round(r)), o.instance_id, -1)
            else:
                for pts, col in faces:
                    cv2.fillPoly(img, [pts], col, lineType=cv2.LINE_AA)
                cv2.fillConvexPoly(ids, geo, o.instance_id)

        joints = self.arm_joints()
        jt_uv, jt_z = cam.project(joints)
        self._draw_arm(img, jt_uv, jt_z)

        return FramePacket(
            frame_id=self.frame_id,
            timestamp=time.perf_counter(),
            rgb=img,
            instance_ids=ids,
            gt_objects={o.instance_id: o.name for o in self.objects},
            gt_labels=list(self._labels),
            robot_skeleton_2d=jt_uv.astype(np.float32),
        )

    def _draw_arm(self, img: np.ndarray, uv: np.ndarray, z: np.ndarray) -> None:
        f = self.camera.f
        widths = (0.12, 0.09, 0.075, 0.055)  # physical link thickness in metres
        p = [tuple(int(round(c)) for c in q) for q in uv]
        for i, wm in enumerate(widths):
            px = max(2, int(f * wm / ((z[i] + z[i + 1]) / 2)))
            cv2.line(img, p[i], p[i + 1], self._shade(YASKAWA_BLUE, 0.7), px + 4, cv2.LINE_AA)
            cv2.line(img, p[i], p[i + 1], YASKAWA_BLUE, px, cv2.LINE_AA)
        for i in range(1, 4):
            r = max(3, int(f * 0.05 / z[i]))
            cv2.circle(img, p[i], r, self._shade(YASKAWA_BLUE, 1.25), -1, cv2.LINE_AA)
        # Parallel-jaw gripper, finger axis rotated by yaw.
        yaw = self.arm.rpy[2]
        axis = np.array([math.cos(yaw), math.sin(yaw), 0.0])
        half = 0.012 + 0.03 * self.arm.gripper
        ee = self.arm.ee
        for s in (-1, 1):
            tip = ee + s * half * axis
            root = tip + np.array([0, 0, 0.055])
            (a, b), _ = self.camera.project(np.stack([root, tip]))
            cv2.line(img, tuple(a.astype(int)), tuple(b.astype(int)), (225, 225, 215), 5, cv2.LINE_AA)
        (a, b), _ = self.camera.project(np.stack([ee + [0, 0, 0.055] - half * axis, ee + [0, 0, 0.055] + half * axis]))
        cv2.line(img, tuple(a.astype(int)), tuple(b.astype(int)), (200, 200, 190), 6, cv2.LINE_AA)
