"""Yaskawa Motoman GP7/GP8 simulator on PyBullet (zlib licence), real vendor meshes.

Drop-in replacement for ``TabletopSim`` (same public API: ``camera``, ``reset``,
``apply_delta``, ``render``, ``state``), so the perception, brain, controller and GUI
code is unchanged.

Architecture (why it stays at 20 Hz even with a slow CPU renderer):

    control thread (this process)              render process (spawned)
    ─────────────────────────────              ────────────────────────
    PyBullet client A: physics + IK            PyBullet client B: same scene, no physics
    apply_delta(): IK -> joints, 12 physics    loop: take NEWEST state (drop stale ones)
      substeps, grasp constraint                     -> set joints / object poses
    after each tick: send ~200-byte state ───►       -> getCameraImage (Tiny or EGL)
    render(): non-blocking; returns newest   ◄───    -> write RGB + instance ids into one of
      frame from shared memory                          3 shared-memory buffers, send index

Rendering a mesh-heavy frame costs 40-100 ms on a CPU, 2-5 ms with a GPU (EGL). It runs
in its own process, so the control loop never waits for it; perception and the GUI get
frames at whatever rate the renderer achieves. ``async_render=False`` renders in-process
and synchronously instead (deterministic, used by tests).
"""

from __future__ import annotations

import logging
import math
import multiprocessing as mp
import tempfile
import time
from dataclasses import dataclass
from multiprocessing import shared_memory
from pathlib import Path

import cv2
import numpy as np

from ..frame_bus import FramePacket
from .motoman_urdf import FINGER_TRAVEL, SPECS, build_urdf
from .simulator import GRASP_RADIUS, GRIPPER_RATE, TABLE_X, TABLE_Y, WORKSPACE_Z, PinholeCamera

log = logging.getLogger(__name__)

TABLE_TOP_Z = 0.0
# Robot stands on the table at the back-right corner, like the reference scene.
BASE_POS = (0.30, 0.80, TABLE_TOP_Z)
BASE_YAW = math.atan2(0.55 - BASE_POS[1], 0.0 - BASE_POS[0])  # face the middle of the table
CAMERA = dict(eye=(-0.42, -0.78, 1.18), target=(0.08, 0.58, 0.30), fov_deg=58.0)
HOME_EE = np.array([0.05, 0.55, 0.30])
# Brighter than the CAD colour so it reads like the reference image under TinyRenderer lighting.
RENDER_BLUE = (0.16, 0.34, 0.86, 1.0)
PHYSICS_HZ = 240


@dataclass(frozen=True)
class ObjSpec:
    name: str
    kind: str
    rgba: tuple[float, float, float, float]
    size: float
    height: float
    xy: tuple[float, float]


OBJECTS = (
    ObjSpec("cube", "cube", (0.86, 0.12, 0.12, 1), 0.05, 0.05, (-0.22, 0.46)),
    ObjSpec("cylinder", "cylinder", (0.14, 0.18, 0.84, 1), 0.05, 0.06, (-0.05, 0.46)),
    ObjSpec("sphere", "sphere", (0.16, 0.78, 0.28, 1), 0.05, 0.05, (0.12, 0.46)),
)


def _label_rects() -> list[tuple[str, tuple[float, float, float, float]]]:
    """World-space rectangles (x0, y0, x1, y1) of the printed labels in front of each object."""
    out = []
    for o in OBJECTS:
        w = 0.016 * len(o.name) + 0.02
        cx, cy = o.xy[0], o.xy[1] - 0.08
        out.append((o.name.upper(), (cx - w / 2, cy - 0.02, cx + w / 2, cy + 0.02)))
    return out


def _table_texture(path: Path, px_per_m: int = 1400) -> None:
    w = int((TABLE_X[1] - TABLE_X[0]) * px_per_m)
    h = int((TABLE_Y[1] - TABLE_Y[0]) * px_per_m)
    img = np.full((h, w, 3), (128, 128, 132), np.uint8)
    for text, (x0, y0, x1, y1) in _label_rects():
        u0, u1 = int((x0 - TABLE_X[0]) * px_per_m), int((x1 - TABLE_X[0]) * px_per_m)
        # image row 0 = far edge (max y) so the text reads upright from the camera
        v0, v1 = int((TABLE_Y[1] - y1) * px_per_m), int((TABLE_Y[1] - y0) * px_per_m)
        cv2.rectangle(img, (u0, v0), (u1, v1), (240, 240, 235), -1)
        scale = (v1 - v0) * 0.026
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 3)
        scale *= min(1.0, 0.9 * (u1 - u0) / tw)
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 3)
        cv2.putText(img, text, ((u0 + u1 - tw) // 2, (v0 + v1 + th) // 2), cv2.FONT_HERSHEY_SIMPLEX, scale,
                    (20, 20, 20), 3, cv2.LINE_AA)
    cv2.imwrite(str(path), img[:, :, ::-1])


def apply_label_texture(p, cid: int, body: int) -> None:
    tex_path = Path(tempfile.gettempdir()) / "vla_dashboard_table_labels.png"
    _table_texture(tex_path)
    p.changeVisualShape(body, -1, textureUniqueId=p.loadTexture(str(tex_path), physicsClientId=cid),
                        physicsClientId=cid)


def build_scene(p, cid: int, model: str, detail: str, with_texture: bool) -> dict:
    """Create table, frame, objects and robot in client ``cid``. Body creation order is
    fixed so both processes get identical body ids."""
    kw = dict(physicsClientId=cid)
    p.setGravity(0, 0, -9.81, **kw)
    p.setTimeStep(1.0 / PHYSICS_HZ, **kw)
    sx, sy = (TABLE_X[1] - TABLE_X[0]) / 2, (TABLE_Y[1] - TABLE_Y[0]) / 2
    cx, cy = (TABLE_X[0] + TABLE_X[1]) / 2, (TABLE_Y[0] + TABLE_Y[1]) / 2

    col = p.createCollisionShape(p.GEOM_BOX, halfExtents=[sx, sy, 0.02], **kw)
    vis = p.createVisualShape(p.GEOM_BOX, halfExtents=[sx, sy, 0.02], rgbaColor=[0.46, 0.46, 0.48, 1], **kw)
    table = p.createMultiBody(0, col, vis, [cx, cy, TABLE_TOP_Z - 0.02], **kw)

    # Thin textured quad on the table top carrying the printed labels.
    z = TABLE_TOP_Z + 0.0008
    verts = [[-sx, -sy, 0], [sx, -sy, 0], [sx, sy, 0], [-sx, sy, 0]]
    quad = p.createVisualShape(p.GEOM_MESH, vertices=verts, indices=[0, 1, 2, 0, 2, 3],
                               uvs=[[0, 0], [1, 0], [1, 1], [0, 1]], normals=[[0, 0, 1]] * 4,
                               rgbaColor=[1, 1, 1, 1], **kw)
    label_body = p.createMultiBody(0, -1, quad, [cx, cy, z], **kw)
    if with_texture:
        apply_label_texture(p, cid, label_body)

    # Aluminium frame: corner posts + top rails (visual only).
    silver, black = [0.84, 0.85, 0.87, 1], [0.08, 0.08, 0.08, 1]
    post_h = 0.06
    corners = [(TABLE_X[0], TABLE_Y[0]), (TABLE_X[1], TABLE_Y[0]), (TABLE_X[1], TABLE_Y[1]), (TABLE_X[0], TABLE_Y[1])]
    for x, y in corners:
        v = p.createVisualShape(p.GEOM_BOX, halfExtents=[0.008, 0.008, post_h / 2], rgbaColor=silver, **kw)
        p.createMultiBody(0, -1, v, [x, y, TABLE_TOP_Z + post_h / 2], **kw)
        c = p.createVisualShape(p.GEOM_BOX, halfExtents=[0.011, 0.011, 0.004], rgbaColor=black, **kw)
        p.createMultiBody(0, -1, c, [x, y, TABLE_TOP_Z + post_h + 0.004], **kw)
    for i in range(4):
        (x0, y0), (x1, y1) = corners[i], corners[(i + 1) % 4]
        length = math.hypot(x1 - x0, y1 - y0)
        v = p.createVisualShape(p.GEOM_BOX, halfExtents=[length / 2, 0.006, 0.006], rgbaColor=silver, **kw)
        p.createMultiBody(0, -1, v, [(x0 + x1) / 2, (y0 + y1) / 2, TABLE_TOP_Z + post_h],
                          p.getQuaternionFromEuler([0, 0, math.atan2(y1 - y0, x1 - x0)]), **kw)

    objects: dict[str, int] = {}
    for o in OBJECTS:
        if o.kind == "cube":
            c = p.createCollisionShape(p.GEOM_BOX, halfExtents=[o.size / 2] * 3, **kw)
            v = p.createVisualShape(p.GEOM_BOX, halfExtents=[o.size / 2] * 3, rgbaColor=o.rgba, **kw)
        elif o.kind == "cylinder":
            c = p.createCollisionShape(p.GEOM_CYLINDER, radius=o.size / 2, height=o.height, **kw)
            v = p.createVisualShape(p.GEOM_CYLINDER, radius=o.size / 2, length=o.height, rgbaColor=o.rgba, **kw)
        else:
            c = p.createCollisionShape(p.GEOM_SPHERE, radius=o.size / 2, **kw)
            v = p.createVisualShape(p.GEOM_SPHERE, radius=o.size / 2, rgbaColor=o.rgba, **kw)
        b = p.createMultiBody(0.08, c, v, [o.xy[0], o.xy[1], TABLE_TOP_Z + o.height / 2], **kw)
        p.changeDynamics(b, -1, lateralFriction=1.0, spinningFriction=0.003, rollingFriction=0.003, **kw)
        objects[o.name] = b

    robot = p.loadURDF(build_urdf(model, detail), list(BASE_POS), p.getQuaternionFromEuler([0, 0, BASE_YAW]),
                       useFixedBase=True, flags=p.URDF_ENABLE_CACHED_GRAPHICS_SHAPES, **kw)
    names = {p.getJointInfo(robot, j, **kw)[1].decode(): j for j in range(p.getNumJoints(robot, **kw))}
    links = {p.getJointInfo(robot, j, **kw)[12].decode(): j for j in range(p.getNumJoints(robot, **kw))}
    for j in range(-1, p.getNumJoints(robot, **kw)):
        p.setCollisionFilterGroupMask(robot, j, 0, 0, **kw)  # robot is kinematic: never pushes the scene
        if j >= 0 and p.getJointInfo(robot, j, **kw)[12].decode().startswith(("link_", "base")):
            p.changeVisualShape(robot, j, rgbaColor=RENDER_BLUE, **kw)
    p.changeVisualShape(robot, -1, rgbaColor=RENDER_BLUE, **kw)

    arm = [names[n] for n in ("joint_1_s", "joint_2_l", "joint_3_u", "joint_4_r", "joint_5_b", "joint_6_t")]
    movable = [j for j in range(p.getNumJoints(robot, **kw)) if p.getJointInfo(robot, j, **kw)[2] != p.JOINT_FIXED]
    return dict(table=table, labels=label_body, robot=robot, objects=objects, arm=arm, movable=movable,
                fingers=[names["finger_left_joint"], names["finger_right_joint"]], tcp=links["tcp"],
                skeleton_links=[links["link_2_l"], links["link_3_u"], links["link_5_b"], links["tcp"]])


def _gradient(h: int, w: int) -> np.ndarray:
    g = np.linspace(226, 172, h, dtype=np.float32)[:, None, None]
    return np.broadcast_to(g, (h, w, 3)).astype(np.uint8)


class _Renderer:
    """Renders a scene in one PyBullet client (used in-process or inside the render process)."""

    def __init__(self, p, cid: int, scene: dict, cam: PinholeCamera, use_egl: bool) -> None:
        self.p, self.cid, self.scene, self.cam = p, cid, scene, cam
        w, h = cam.width, cam.height
        fov_v = math.degrees(2 * math.atan(h / 2 / cam.f))
        self.view = p.computeViewMatrix(cam.eye.tolist(), (cam.eye + cam.R[2]).tolist(), [0, 0, 1])
        self.proj = p.computeProjectionMatrixFOV(fov_v, w / h, 0.05, 6.0)
        self.renderer = p.ER_TINY_RENDERER
        if use_egl:
            try:
                import pkgutil

                egl = pkgutil.get_loader("eglRenderer")
                if egl is not None and p.loadPlugin(egl.get_filename(), "_eglRendererPlugin", physicsClientId=cid) >= 0:
                    self.renderer = p.ER_BULLET_HARDWARE_OPENGL
            except Exception as exc:  # noqa: BLE001
                log.warning("EGL renderer unavailable (%s); using TinyRenderer", exc)
        self.bg = _gradient(h, w)
        n = max([scene["robot"], scene["table"], *scene["objects"].values()]) + 2
        self.lut = np.zeros(n, np.uint8)  # body id + 1 -> instance id (0 = not an object)
        for i, b in enumerate(scene["objects"].values(), start=1):
            self.lut[b + 1] = i

    def render(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        p, w, h = self.p, self.cam.width, self.cam.height
        _, _, rgba, _, seg = p.getCameraImage(
            w, h, self.view, self.proj, renderer=self.renderer, shadow=1, lightDirection=[0.6, -1.0, 1.6],
            lightAmbientCoeff=0.55, lightDiffuseCoeff=0.55, lightSpecularCoeff=0.25, physicsClientId=self.cid)
        rgb = np.reshape(rgba, (h, w, 4))[:, :, :3].astype(np.uint8)
        seg = np.reshape(seg, (h, w))
        bg = seg < 0
        rgb[bg] = self.bg[bg]  # studio-grey gradient behind the scene, like the reference
        ids = self.lut[np.clip(seg, -1, len(self.lut) - 2) + 1]
        pts = [p.getLinkState(self.scene["robot"], li, physicsClientId=self.cid)[4]
               for li in self.scene["skeleton_links"]]
        base = p.getBasePositionAndOrientation(self.scene["robot"], physicsClientId=self.cid)[0]
        skel, _ = self.cam.project(np.array([base, *pts]))
        return rgb, ids, skel.astype(np.float32)


def _apply_state(p, cid: int, scene: dict, state) -> None:
    q, poses = state
    for j, v in zip(scene["movable"], q):
        p.resetJointState(scene["robot"], j, v, physicsClientId=cid)
    for b, (pos, orn) in zip(scene["objects"].values(), poses):
        p.resetBasePositionAndOrientation(b, pos, orn, physicsClientId=cid)


def _render_server(conn, shm_names: list[str], params: dict) -> None:
    """Entry point of the render process."""
    import pybullet as p

    cid = p.connect(p.DIRECT)
    scene = build_scene(p, cid, params["model"], params["detail"], with_texture=True)
    cam = PinholeCamera(params["width"], params["height"], **CAMERA)
    r = _Renderer(p, cid, scene, cam, params["use_egl"])
    h, w = params["height"], params["width"]
    shms = [shared_memory.SharedMemory(name=n) for n in shm_names]
    bufs = [np.ndarray((h, w, 4), np.uint8, buffer=s.buf) for s in shms]
    k = 0
    try:
        while True:
            msg = conn.recv()
            while conn.poll():  # latest wins: skip states that arrived while we were rendering
                msg = conn.recv()
            if msg is None:
                break
            seq, state = msg
            _apply_state(p, cid, scene, state)
            rgb, ids, skel = r.render()
            bufs[k][:, :, :3] = rgb
            bufs[k][:, :, 3] = ids
            conn.send((seq, k, time.perf_counter(), skel))
            k = (k + 1) % len(bufs)
    except (EOFError, KeyboardInterrupt, BrokenPipeError):
        pass
    finally:
        for s in shms:
            s.close()
        p.disconnect(cid)


class PyBulletSim:
    """Same public API as ``TabletopSim``."""

    def __init__(self, width: int = 640, height: int = 480, model: str = "gp7", detail: str = "fast",
                 control_hz: float = 20.0, async_render: bool = True, use_egl: bool = False) -> None:
        import pybullet as p

        self.p = p
        self.width, self.height, self.model = width, height, model
        self.spec = SPECS[model]
        self.camera = PinholeCamera(width, height, **CAMERA)
        self.substeps = max(1, round(PHYSICS_HZ / control_hz))
        self.cid = p.connect(p.DIRECT)
        self.scene = build_scene(p, self.cid, model, detail, with_texture=not async_render)
        self._labels = self._project_labels()
        self.frame_id = 0
        self._seq = 0
        self._last: FramePacket | None = None
        self._proc = self._conn = None
        self._shms: list[shared_memory.SharedMemory] = []
        self._local: _Renderer | None = None
        lim = [(math.radians(lo), math.radians(hi)) for lo, hi in self.spec.limits]
        n = len(self.scene["movable"])
        self._lower = [lo for lo, _ in lim] + [0.0] * (n - 6)
        self._upper = [hi for _, hi in lim] + [FINGER_TRAVEL] * (n - 6)
        self._ranges = [hi - lo for lo, hi in zip(self._lower, self._upper)]
        self._rest = [0.0, 0.35, 0.15, 0.0, -1.2, 0.0] + [0.0] * (n - 6)
        if async_render:
            self._start_render_process(detail, use_egl)
        else:
            self._local = _Renderer(p, self.cid, self.scene, self.camera, use_egl)
        self.reset()

    # ------------------------------------------------------------------ render process
    def _start_render_process(self, detail: str, use_egl: bool) -> None:
        size = self.width * self.height * 4
        self._shms = [shared_memory.SharedMemory(create=True, size=size) for _ in range(3)]
        ctx = mp.get_context("spawn")  # never fork a process that has Qt / PyBullet state
        self._conn, child = ctx.Pipe()
        params = dict(model=self.model, detail=detail, width=self.width, height=self.height, use_egl=use_egl)
        self._proc = ctx.Process(target=_render_server, args=(child, [s.name for s in self._shms], params),
                                 name="vla-render", daemon=True)
        self._proc.start()
        log.info("render process started (pid %s)", self._proc.pid)

    def close(self) -> None:
        if self._proc is not None and self._conn is not None:
            try:
                self._conn.send(None)
            except (BrokenPipeError, OSError):
                pass
            self._proc.join(timeout=2)
            if self._proc.is_alive():
                self._proc.terminate()
            self._proc = None
        for s in self._shms:
            s.close()
            s.unlink()
        self._shms = []
        try:
            self.p.disconnect(self.cid)
        except Exception:  # noqa: BLE001
            pass

    def __del__(self) -> None:  # best effort; Engine.shutdown() calls close() explicitly
        try:
            self.close()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ lifecycle
    def reset(self) -> None:
        p, kw = self.p, dict(physicsClientId=self.cid)
        if getattr(self, "_constraint", None) is not None:  # drop a grasp left over from the last episode
            p.removeConstraint(self._constraint, **kw)
        self.ee = HOME_EE.copy()
        self.rpy = np.zeros(3)
        self.gripper = 1.0
        self.holding: str | None = None
        self._constraint: int | None = None
        for o in OBJECTS:
            p.resetBasePositionAndOrientation(self.scene["objects"][o.name],
                                              [o.xy[0], o.xy[1], TABLE_TOP_Z + o.height / 2], [0, 0, 0, 1], **kw)
            p.resetBaseVelocity(self.scene["objects"][o.name], [0, 0, 0], [0, 0, 0], **kw)
        for j, q in zip(self.scene["movable"], self._rest):
            p.resetJointState(self.scene["robot"], j, q, **kw)
        for _ in range(4):
            self._solve_ik(self.ee)
        self.ee = self._tcp_pos()
        self._set_fingers()
        self._push_state()
        if self._proc is not None and self._last is None:
            self._last = self._placeholder()  # never block the caller (GUI start-up) on the renderer

    def _placeholder(self) -> FramePacket:
        rgb = _gradient(self.height, self.width).copy()
        cv2.putText(rgb, "starting renderer...", (self.width // 2 - 120, self.height // 2), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (90, 90, 90), 2, cv2.LINE_AA)
        return FramePacket(frame_id=0, timestamp=time.perf_counter(), rgb=rgb, instance_ids=None)

    def wait_first_frame(self, timeout: float = 20.0) -> None:
        """Block until the render process has delivered a real frame (tests / scripts)."""
        t = time.monotonic()
        while self._last is None or self._last.frame_id == 0:
            if self._poll_frame():
                return
            if time.monotonic() - t > timeout or not self._proc.is_alive():
                raise RuntimeError("render process produced no frame")
            time.sleep(0.01)

    # ------------------------------------------------------------------ kinematics
    def _tcp_pos(self) -> np.ndarray:
        return np.array(self.p.getLinkState(self.scene["robot"], self.scene["tcp"], computeForwardKinematics=True,
                                            physicsClientId=self.cid)[4])

    def _target_orn(self):
        r, pch, y = self.rpy
        return self.p.getQuaternionFromEuler([math.pi + r, pch, y])  # tool z pointing down, yaw about world z

    def _solve_ik(self, target: np.ndarray) -> float:
        p, rob = self.p, self.scene["robot"]
        q = p.calculateInverseKinematics(
            rob, self.scene["tcp"], target.tolist(), self._target_orn(), lowerLimits=self._lower,
            upperLimits=self._upper, jointRanges=self._ranges, restPoses=self._rest, maxNumIterations=60,
            residualThreshold=1e-5, physicsClientId=self.cid)
        for j, v in zip(self.scene["arm"], q[:6]):
            p.resetJointState(rob, j, v, physicsClientId=self.cid)
        return float(np.linalg.norm(self._tcp_pos() - target))

    def _solve_ik_robust(self, target: np.ndarray) -> float:
        """Warm-started IK; if that converges to a bad local minimum, reseed from the rest pose."""
        err = self._solve_ik(target)
        if err > 0.004:
            err = self._solve_ik(target)
        if err > 0.004:
            for j, v in zip(self.scene["arm"], self._rest):
                self.p.resetJointState(self.scene["robot"], j, v, physicsClientId=self.cid)
            for _ in range(3):
                err = self._solve_ik(target)
        return err

    def _arm_q(self) -> list[float]:
        return [self.p.getJointState(self.scene["robot"], j, physicsClientId=self.cid)[0] for j in self.scene["arm"]]

    def _set_fingers(self) -> None:
        q = FINGER_TRAVEL * self.gripper
        if self.holding is not None:
            q = max(q, 0.026)
        for j in self.scene["fingers"]:
            self.p.resetJointState(self.scene["robot"], j, q, physicsClientId=self.cid)

    # ------------------------------------------------------------------ dynamics
    def apply_delta(self, d: np.ndarray) -> None:
        p, kw = self.p, dict(physicsClientId=self.cid)
        if not np.any(d[:6]):  # hold: keep joints exactly where they are (no IK re-solve drift)
            self._step_gripper_and_physics(float(d[6]))
            return
        target = self.ee + d[:3]
        target[0] = np.clip(target[0], *TABLE_X)
        target[1] = np.clip(target[1], *TABLE_Y)
        target[2] = np.clip(target[2], *WORKSPACE_Z)
        self.rpy = (self.rpy + d[3:6] + math.pi) % (2 * math.pi) - math.pi
        prev_q = self._arm_q()
        err = self._solve_ik_robust(target)
        if err > 0.015:  # unreachable: stay where we are
            for j, v in zip(self.scene["arm"], prev_q):
                p.resetJointState(self.scene["robot"], j, v, **kw)
        self.ee = self._tcp_pos()
        self._step_gripper_and_physics(float(d[6]))

    def _step_gripper_and_physics(self, dgrip: float) -> None:
        p, kw = self.p, dict(physicsClientId=self.cid)
        self.gripper = float(np.clip(self.gripper + GRIPPER_RATE * dgrip, 0.0, 1.0))
        if self.holding is None and self.gripper < 0.4:
            name = self._nearest(GRASP_RADIUS)
            if name is not None:
                self._grasp(name)
        if self.holding is not None:
            self.gripper = max(self.gripper, 0.3)
            if self.gripper > 0.6:
                p.removeConstraint(self._constraint, **kw)
                self._constraint, self.holding = None, None
        self._set_fingers()
        for _ in range(self.substeps):
            p.stepSimulation(**kw)
        self._push_state()

    def _nearest(self, radius: float) -> str | None:
        best, best_d = None, radius
        for name, b in self.scene["objects"].items():
            pos = np.array(self.p.getBasePositionAndOrientation(b, physicsClientId=self.cid)[0])
            dist = float(np.linalg.norm(pos - self.ee))
            if dist < best_d:
                best, best_d = name, dist
        return best

    def _grasp(self, name: str) -> None:
        """Rigidly attach the object to the TCP, keeping its current relative pose."""
        p, kw = self.p, dict(physicsClientId=self.cid)
        rob, tcp, b = self.scene["robot"], self.scene["tcp"], self.scene["objects"][name]
        ls = p.getLinkState(rob, tcp, **kw)
        tpos, torn = ls[4], ls[5]
        opos, oorn = p.getBasePositionAndOrientation(b, **kw)
        inv_pos, inv_orn = p.invertTransform(tpos, torn)
        rel_pos, rel_orn = p.multiplyTransforms(inv_pos, inv_orn, opos, oorn)
        self._constraint = p.createConstraint(rob, tcp, b, -1, p.JOINT_FIXED, [0, 0, 0], rel_pos, [0, 0, 0],
                                              parentFrameOrientation=rel_orn, **kw)
        p.changeConstraint(self._constraint, maxForce=200, **kw)
        self.holding = name

    # ------------------------------------------------------------------ state / frames
    def _snapshot(self):
        p, kw = self.p, dict(physicsClientId=self.cid)
        q = [p.getJointState(self.scene["robot"], j, **kw)[0] for j in self.scene["movable"]]
        poses = [p.getBasePositionAndOrientation(b, **kw) for b in self.scene["objects"].values()]
        return q, poses

    def _push_state(self) -> None:
        if self._conn is not None:
            self._seq += 1
            try:
                self._conn.send((self._seq, self._snapshot()))
            except (BrokenPipeError, OSError) as exc:
                self._fallback_to_local(repr(exc))

    def _fallback_to_local(self, reason: str) -> None:
        """Render process died: keep running by rendering in-process (slower, but alive)."""
        log.error("render process lost (%s); falling back to in-process rendering", reason)
        apply_label_texture(self.p, self.cid, self.scene["labels"])
        self._local = _Renderer(self.p, self.cid, self.scene, self.camera, use_egl=False)
        self._proc, self._conn = None, None

    def _poll_frame(self) -> bool:
        got = None
        try:
            while self._conn.poll():
                got = self._conn.recv()
        except (EOFError, OSError) as exc:
            self._fallback_to_local(repr(exc))
            return False
        if got is None:
            return False
        _, k, ts, skel = got
        buf = np.ndarray((self.height, self.width, 4), np.uint8, buffer=self._shms[k].buf)
        rgb = np.ascontiguousarray(buf[:, :, :3])  # copy out: the buffer will be reused
        ids = buf[:, :, 3].copy()
        self.frame_id += 1
        self._last = self._packet(rgb, ids, skel, ts)
        return True

    def _packet(self, rgb, ids, skel, ts) -> FramePacket:
        return FramePacket(
            frame_id=self.frame_id, timestamp=ts, rgb=rgb, instance_ids=ids,
            gt_objects={i: o.name for i, o in enumerate(OBJECTS, start=1)},
            gt_labels=list(self._labels), robot_skeleton_2d=skel)

    def render(self) -> FramePacket:
        """Newest frame. Async mode: never blocks (returns the previous packet if no new
        frame is ready; ``frame_id`` tells consumers whether it is new)."""
        if self._proc is not None and not self._proc.is_alive():
            self._fallback_to_local(f"exit code {self._proc.exitcode}")
        if self._local is not None:
            rgb, ids, skel = self._local.render()
            self.frame_id += 1
            return self._packet(rgb, ids, skel, time.perf_counter())
        self._poll_frame()
        return self._last

    def _project_labels(self):
        out = []
        for text, (x0, y0, x1, y1) in _label_rects():
            uv, _ = self.camera.project(np.array([[x0, y0, 0], [x1, y0, 0], [x1, y1, 0], [x0, y1, 0]], float))
            out.append((text, (float(uv[:, 0].min()), float(uv[:, 1].min()),
                               float(uv[:, 0].max()), float(uv[:, 1].max()))))
        return out

    def state(self) -> dict:
        objs = {name: np.array(self.p.getBasePositionAndOrientation(b, physicsClientId=self.cid)[0])
                for name, b in self.scene["objects"].items()}
        return {"ee": self.ee.copy(), "rpy": self.rpy.copy(), "gripper": self.gripper, "holding": self.holding,
                "objects": objs}
