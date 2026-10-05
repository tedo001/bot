"""Yaskawa Motoman GP7/GP8 simulator on MuJoCo (Apache-2.0), real vendor CAD meshes.

Why a second physics backend: ``pip install mujoco`` ships prebuilt wheels for Windows,
Linux and macOS, while PyBullet has no Windows wheels (it needs a C++ compiler there).
Same public API as ``TabletopSim`` / ``PyBulletSim`` and the same scene (sim/scene.py),
so perception, the learned policy and the GUI work unchanged.

* Arm: kinematic (joint angles set from damped-least-squares IK on the TCP site), so
  it tracks commands exactly and never knocks objects over by accident.
* Objects: free rigid bodies with gravity, friction and contacts (real stacking).
* Grasp: a held object follows the TCP rigidly; on release it is handed back to physics.
* Rendering: MuJoCo's OpenGL renderer (GPU on a normal PC; EGL when headless) plus a
  segmentation pass for the instance masks the mock perception uses. By default it runs
  in its own thread with its own copy of the simulation state: after every physics tick
  the control loop hands over a ~30-number snapshot, and ``render()`` just picks up the
  newest finished frame, so physics and the policy keep 20 Hz however slow the GPU/CPU
  renderer is (MuJoCo releases the GIL while rendering, so this is truly parallel).
"""

from __future__ import annotations

import logging
import math
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

from ..frame_bus import FramePacket
from .motoman_urdf import (ASSETS, FINGER_LEN, FINGER_TRAVEL, GRIPPER_PALM_LEN, SPECS, TCP_OFFSET)
from .scene import (BASE_POS, BASE_YAW, CAMERA, HOME_EE, OBJECTS, RENDER_BLUE, TABLE_TOP_Z, _gradient, _label_rects,
                    _table_texture)
from .simulator import GRASP_RADIUS, GRIPPER_RATE, TABLE_X, TABLE_Y, WORKSPACE_Z, PinholeCamera

log = logging.getLogger(__name__)

TIMESTEP = 0.002
ARM_JOINTS = ("joint_1_s", "joint_2_l", "joint_3_u", "joint_4_r", "joint_5_b", "joint_6_t")
REST_Q = np.array([0.0, 0.35, 0.15, 0.0, -1.2, 0.0])


def _select_gl_backend() -> None:
    """Headless Linux has no window system: use EGL unless the user chose a backend."""
    if sys.platform.startswith("linux") and "MUJOCO_GL" not in os.environ and not os.environ.get("DISPLAY"):
        os.environ["MUJOCO_GL"] = "egl"


def _quat_from_matrix(R: np.ndarray) -> np.ndarray:
    """Rotation matrix -> quaternion (w, x, y, z)."""
    t = np.trace(R)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        q = [0.25 * s, (R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s]
    else:
        i = int(np.argmax(np.diag(R)))
        j, k = (i + 1) % 3, (i + 2) % 3
        s = math.sqrt(1.0 + R[i, i] - R[j, j] - R[k, k]) * 2
        q = [0.0] * 4
        q[0] = (R[k, j] - R[j, k]) / s
        q[i + 1] = 0.25 * s
        q[j + 1] = (R[j, i] + R[i, j]) / s
        q[k + 1] = (R[k, i] + R[i, k]) / s
    q = np.array(q)
    return q / np.linalg.norm(q)


def _rpy_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """URDF / PyBullet convention: fixed-axis XYZ, R = Rz(yaw) @ Ry(pitch) @ Rx(roll)."""
    cr, sr, cp, sp, cy, sy = math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch), math.cos(yaw), \
        math.sin(yaw)
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return rz @ ry @ rx


def _f(v) -> str:
    return " ".join(f"{x:.6g}" for x in v)


def build_mjcf(model: str = "gp7", detail: str = "fast", camera: PinholeCamera | None = None) -> str:
    spec = SPECS[model]
    visual_dir = "visual_fast" if detail == "fast" else "visual"
    ext = "obj" if detail == "fast" else "stl"
    mesh_dir = ASSETS / spec.name / visual_dir
    links = ("base_link", "link_1_s", "link_2_l", "link_3_u", "link_4_r", "link_5_b", "link_6_t")
    meshes = "\n".join(f'    <mesh name="{ln}" file="{(mesh_dir / f"{spec.name}_{ln}.{ext}").as_posix()}"/>'
                       for ln in links)
    lim = [(math.radians(lo), math.radians(hi)) for lo, hi in spec.limits]
    tex = Path(tempfile.gettempdir()) / "vla_dashboard_table_labels.png"
    _table_texture(tex)
    cam = camera or PinholeCamera(640, 480, **CAMERA)
    right, down = cam.R[0], cam.R[1]
    fovy = math.degrees(2 * math.atan(cam.height / 2 / cam.f))
    blue = _f(RENDER_BLUE)
    tool_q = _f(_quat_from_matrix(_rpy_matrix(math.pi, -math.pi / 2, 0.0)))
    base_q = _f([math.cos(BASE_YAW / 2), 0, 0, math.sin(BASE_YAW / 2)])
    sx, sy = (TABLE_X[1] - TABLE_X[0]) / 2, (TABLE_Y[1] - TABLE_Y[0]) / 2
    cx, cy = (TABLE_X[0] + TABLE_X[1]) / 2, (TABLE_Y[0] + TABLE_Y[1]) / 2
    corners = [(TABLE_X[0], TABLE_Y[0]), (TABLE_X[1], TABLE_Y[0]), (TABLE_X[1], TABLE_Y[1]), (TABLE_X[0], TABLE_Y[1])]
    frame = []
    for i, (x, y) in enumerate(corners):
        frame.append(f'<geom type="box" size="0.008 0.008 0.03" pos="{x} {y} {TABLE_TOP_Z + 0.03}" material="alu" '
                     'contype="0" conaffinity="0"/>')
        frame.append(f'<geom type="box" size="0.011 0.011 0.004" pos="{x} {y} {TABLE_TOP_Z + 0.064}" '
                     'rgba="0.08 0.08 0.08 1" contype="0" conaffinity="0"/>')
        (x0, y0), (x1, y1) = corners[i], corners[(i + 1) % 4]
        half = math.hypot(x1 - x0, y1 - y0) / 2
        ang = math.atan2(y1 - y0, x1 - x0)
        frame.append(f'<geom type="box" size="{half} 0.006 0.006" pos="{(x0 + x1) / 2} {(y0 + y1) / 2} '
                     f'{TABLE_TOP_Z + 0.06}" quat="{_f([math.cos(ang / 2), 0, 0, math.sin(ang / 2)])}" material="alu" '
                     'contype="0" conaffinity="0"/>')
    objs = []
    for o in OBJECTS:
        if o.kind == "cube":
            g = f'type="box" size="{o.size / 2} {o.size / 2} {o.size / 2}"'
        elif o.kind == "cylinder":
            g = f'type="cylinder" size="{o.size / 2} {o.height / 2}"'
        else:
            g = f'type="sphere" size="{o.size / 2}" condim="6" friction="1 0.005 0.002"'
        objs.append(f'''    <body name="{o.name}" pos="{o.xy[0]} {o.xy[1]} {TABLE_TOP_Z + o.height / 2}">
      <freejoint name="{o.name}_free"/>
      <geom name="{o.name}" {g} mass="0.08" rgba="{_f(o.rgba)}"/>
    </body>''')
    palm_top = 0.015 + GRIPPER_PALM_LEN
    grey, dark = "0.82 0.82 0.8 1", "0.35 0.35 0.37 1"
    arm = f'''    <body name="base_link" pos="{_f(BASE_POS)}" quat="{base_q}">
      <geom mesh="base_link" class="arm"/>
      <body name="link_1_s" pos="0 0 0.330">
        <joint name="joint_1_s" axis="0 0 1" range="{lim[0][0]} {lim[0][1]}"/>
        <geom mesh="link_1_s" class="arm"/>
        <body name="link_2_l" pos="0.040 0 0">
          <joint name="joint_2_l" axis="0 1 0" range="{lim[1][0]} {lim[1][1]}"/>
          <geom mesh="link_2_l" class="arm"/>
          <body name="link_3_u" pos="0 0 {spec.upper_arm}">
            <joint name="joint_3_u" axis="0 -1 0" range="{lim[2][0]} {lim[2][1]}"/>
            <geom mesh="link_3_u" class="arm"/>
            <body name="link_4_r" pos="{spec.forearm} 0 0.040">
              <joint name="joint_4_r" axis="-1 0 0" range="{lim[3][0]} {lim[3][1]}"/>
              <geom mesh="link_4_r" class="arm"/>
              <body name="link_5_b">
                <joint name="joint_5_b" axis="0 -1 0" range="{lim[4][0]} {lim[4][1]}"/>
                <geom mesh="link_5_b" class="arm"/>
                <body name="link_6_t">
                  <joint name="joint_6_t" axis="-1 0 0" range="{lim[5][0]} {lim[5][1]}"/>
                  <geom mesh="link_6_t" class="arm"/>
                  <body name="tool0" pos="0.080 0 0" quat="{tool_q}">
                    <geom type="box" size="0.025 0.025 0.0075" pos="0 0 0.0075" rgba="{dark}" class="grip"/>
                    <geom type="box" size="0.025 0.05 {GRIPPER_PALM_LEN / 2}" pos="0 0 {0.015 + GRIPPER_PALM_LEN / 2}"
                          rgba="{grey}" class="grip"/>
                    <body name="finger_left" pos="0 0.006 {palm_top}">
                      <joint name="finger_left" type="slide" axis="0 1 0" range="0 {FINGER_TRAVEL}"/>
                      <geom type="box" size="0.01 0.006 {FINGER_LEN / 2}" pos="0 0 {FINGER_LEN / 2}" rgba="{grey}"
                            class="grip"/>
                    </body>
                    <body name="finger_right" pos="0 -0.006 {palm_top}">
                      <joint name="finger_right" type="slide" axis="0 -1 0" range="0 {FINGER_TRAVEL}"/>
                      <geom type="box" size="0.01 0.006 {FINGER_LEN / 2}" pos="0 0 {FINGER_LEN / 2}" rgba="{grey}"
                            class="grip"/>
                    </body>
                    <site name="tcp" pos="0 0 {TCP_OFFSET}" size="0.004"/>
                  </body>
                </body>
              </body>
            </body>
          </body>
        </body>
      </body>
    </body>'''
    return f'''<mujoco model="motoman_{spec.name}_tabletop">
  <compiler angle="radian" autolimits="true"/>
  <option timestep="{TIMESTEP}" gravity="0 0 -9.81"/>
  <visual>
    <global offwidth="1920" offheight="1080"/>
    <quality shadowsize="2048"/>
    <headlight ambient="0.45 0.45 0.45" diffuse="0.45 0.45 0.45" specular="0.1 0.1 0.1"/>
  </visual>
  <default>
    <default class="arm"><geom type="mesh" contype="0" conaffinity="0" rgba="{blue}"/></default>
    <default class="grip"><geom contype="0" conaffinity="0"/></default>
    <joint damping="0" armature="0.01"/>
  </default>
  <asset>
{meshes}
    <texture name="labels" type="2d" file="{tex.as_posix()}"/>
    <material name="labels" texture="labels" texrepeat="1 1" texuniform="false"/>
    <material name="alu" rgba="0.84 0.85 0.87 1" specular="0.6"/>
  </asset>
  <worldbody>
    <light pos="0.3 -0.6 1.8" dir="-0.3 0.6 -1" diffuse="0.55 0.55 0.55" castshadow="true"/>
    <camera name="main" pos="{_f(cam.eye)}" xyaxes="{_f(right)} {_f(-down)}" fovy="{fovy:.6g}"/>
    <geom name="table" type="box" size="{sx} {sy} 0.02" pos="{cx} {cy} {TABLE_TOP_Z - 0.02}" rgba="0.46 0.46 0.48 1"
          friction="1 0.005 0.002"/>
    <geom name="table_labels" type="plane" size="{sx} {sy} 0.01" pos="{cx} {cy} {TABLE_TOP_Z + 0.0008}"
          material="labels" contype="0" conaffinity="0"/>
    {" ".join(frame)}
{chr(10).join(objs)}
{arm}
  </worldbody>
</mujoco>
'''


class MuJoCoSim:
    """Same public API as ``TabletopSim`` / ``PyBulletSim``."""

    def __init__(self, width: int = 640, height: int = 480, model: str = "gp7", detail: str = "fast",
                 control_hz: float = 20.0, async_render: bool = True) -> None:
        _select_gl_backend()
        import mujoco

        self.mj = mujoco
        self.width, self.height, self.model_name = width, height, model
        self.spec = SPECS[model]
        self.camera = PinholeCamera(width, height, **CAMERA)
        self.m = mujoco.MjModel.from_xml_string(build_mjcf(model, detail, self.camera))
        self.d = mujoco.MjData(self.m)
        self.substeps = max(1, round(1.0 / (control_hz * TIMESTEP)))
        jid = lambda n: mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_JOINT, n)  # noqa: E731
        self.arm_qadr = np.array([self.m.jnt_qposadr[jid(n)] for n in ARM_JOINTS])
        self.arm_dof = np.array([self.m.jnt_dofadr[jid(n)] for n in ARM_JOINTS])
        self.finger_qadr = [self.m.jnt_qposadr[jid(n)] for n in ("finger_left", "finger_right")]
        self.lo = np.array([self.m.jnt_range[jid(n)][0] for n in ARM_JOINTS])
        self.hi = np.array([self.m.jnt_range[jid(n)][1] for n in ARM_JOINTS])
        self.tcp = mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_SITE, "tcp")
        self.obj_body = {o.name: mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_BODY, o.name) for o in OBJECTS}
        self.obj_qadr = {o.name: self.m.jnt_qposadr[jid(f"{o.name}_free")] for o in OBJECTS}
        self.obj_dadr = {o.name: self.m.jnt_dofadr[jid(f"{o.name}_free")] for o in OBJECTS}
        self.skeleton_bodies = [mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_BODY, n)
                                for n in ("base_link", "link_2_l", "link_3_u", "link_5_b")]
        geom_id = {o.name: mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_GEOM, o.name) for o in OBJECTS}
        self.lut = np.zeros(self.m.ngeom + 1, np.uint8)  # geom id + 1 -> instance id
        for i, o in enumerate(OBJECTS, start=1):
            self.lut[geom_id[o.name] + 1] = i
        self._labels = self._project_labels()
        self._bg = _gradient(height, width)
        self._renderer = None
        self._last: FramePacket | None = None
        self._render_ema = 0.0  # seconds per rendered frame
        self._last_render = -1e9
        self.frame_id = 0
        self.render_error: str | None = None
        self._async = async_render
        self._cond = threading.Condition()
        self._snap: np.ndarray | None = None  # newest qpos for the render thread
        self._snap_seq = 0
        self._closing = False
        self._wanted = False  # render thread idles until someone actually asks for frames
        self._thread: threading.Thread | None = None
        self.reset()
        if self._async:
            self._rd = mujoco.MjData(self.m)  # render thread's own copy: no data races with physics
            self._thread = threading.Thread(target=self._render_loop, name="mujoco-render", daemon=True)
            self._thread.start()

    # ------------------------------------------------------------------ lifecycle
    def reset(self, layout: dict[str, tuple[float, float]] | None = None, render_static: bool = True) -> None:
        mj, d = self.mj, self.d
        layout = layout or {}
        mj.mj_resetData(self.m, d)
        for o in OBJECTS:
            x, y = layout.get(o.name, o.xy)
            a = self.obj_qadr[o.name]
            d.qpos[a:a + 7] = [x, y, TABLE_TOP_Z + o.height / 2, 1, 0, 0, 0]
        d.qpos[self.arm_qadr] = REST_Q
        self.rpy = np.zeros(3)
        self.gripper = 1.0
        self.holding: str | None = None
        self._rel = None
        for _ in range(3):
            self._solve_ik(HOME_EE, iters=200)
        self._set_fingers()
        mj.mj_forward(self.m, d)
        self.ee = self._tcp_pos()
        self._last_render = -1e9  # render the reset scene right away
        self._push_snapshot()

    def close(self) -> None:
        if self._thread is not None:
            with self._cond:
                self._closing = True
                self._cond.notify_all()
            self._thread.join(timeout=3)
            self._thread = None
            return
        if self._renderer is not None:
            try:
                self._renderer.close()
            except Exception:  # noqa: BLE001
                pass
            self._renderer = None

    # ------------------------------------------------------------------ kinematics
    def _tcp_pos(self) -> np.ndarray:
        return self.d.site_xpos[self.tcp].copy()

    def _target_R(self) -> np.ndarray:
        r, p, y = self.rpy
        return _rpy_matrix(math.pi + r, p, y)  # tool z down, yaw about world z

    def _solve_ik(self, target: np.ndarray, iters: int = 60) -> float:
        """Damped least squares on position + orientation, warm-started from the current pose,
        with a weak pull toward the rest pose so the arm stays in the elbow-up configuration."""
        mj, m, d = self.mj, self.m, self.d
        Rt = self._target_R()
        jacp, jacr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        q = d.qpos[self.arm_qadr].copy()
        err = 1.0
        for _ in range(iters):
            mj.mj_kinematics(m, d)
            mj.mj_comPos(m, d)
            pos = d.site_xpos[self.tcp]
            R = d.site_xmat[self.tcp].reshape(3, 3)
            e_p = target - pos
            e_r = 0.5 * (np.cross(R[:, 0], Rt[:, 0]) + np.cross(R[:, 1], Rt[:, 1]) + np.cross(R[:, 2], Rt[:, 2]))
            err = float(np.linalg.norm(e_p))
            if err < 2e-4 and np.linalg.norm(e_r) < 2e-3:
                break
            mj.mj_jacSite(m, d, jacp, jacr, self.tcp)
            J = np.vstack([jacp[:, self.arm_dof], 0.5 * jacr[:, self.arm_dof]])
            e = np.concatenate([e_p, 0.5 * e_r])
            JJt = J @ J.T + (0.02 ** 2) * np.eye(6)
            dq = J.T @ np.linalg.solve(JJt, e)
            null = np.eye(6) - np.linalg.pinv(J) @ J
            dq += null @ (0.05 * (REST_Q - q))
            q = np.clip(q + np.clip(dq, -0.2, 0.2), self.lo, self.hi)
            d.qpos[self.arm_qadr] = q
        mj.mj_kinematics(m, d)
        return float(np.linalg.norm(target - d.site_xpos[self.tcp])) if err >= 2e-4 else err

    def _set_fingers(self) -> None:
        q = FINGER_TRAVEL * self.gripper
        if self.holding is not None:
            q = max(q, 0.026)
        for a in self.finger_qadr:
            self.d.qpos[a] = q

    # ------------------------------------------------------------------ dynamics
    def apply_delta(self, delta: np.ndarray) -> None:
        mj, d = self.mj, self.d
        if np.any(delta[:6]):  # zero motion (E-STOP / hold) keeps the joints exactly where they are
            target = self.ee + delta[:3]
            target[0] = np.clip(target[0], *TABLE_X)
            target[1] = np.clip(target[1], *TABLE_Y)
            target[2] = np.clip(target[2], *WORKSPACE_Z)
            self.rpy = (self.rpy + delta[3:6] + math.pi) % (2 * math.pi) - math.pi
            prev = d.qpos[self.arm_qadr].copy()
            if self._solve_ik(target) > 0.015:  # unreachable: stay where we are
                d.qpos[self.arm_qadr] = prev
                mj.mj_kinematics(self.m, d)
            self.ee = self._tcp_pos()
        self.gripper = float(np.clip(self.gripper + GRIPPER_RATE * delta[6], 0.0, 1.0))
        if self.holding is None and self.gripper < 0.4:
            name = self._nearest(GRASP_RADIUS)
            if name is not None:
                self._grasp(name)
        if self.holding is not None:
            self.gripper = max(self.gripper, 0.3)
            if self.gripper > 0.6:
                self.holding, self._rel = None, None
        self._set_fingers()
        q_arm = d.qpos[self.arm_qadr].copy()
        q_fing = [d.qpos[a] for a in self.finger_qadr]
        for _ in range(self.substeps):
            d.qpos[self.arm_qadr] = q_arm  # kinematic arm: hold the commanded joints
            d.qvel[self.arm_dof] = 0.0
            for a, v in zip(self.finger_qadr, q_fing):
                d.qpos[a] = v
            if self.holding is not None:
                self._carry()
            mj.mj_step(self.m, d)
        mj.mj_forward(self.m, d)
        self._push_snapshot()

    def _nearest(self, radius: float) -> str | None:
        best, best_d = None, radius
        for name, b in self.obj_body.items():
            dist = float(np.linalg.norm(self.d.xpos[b] - self.ee))
            if dist < best_d:
                best, best_d = name, dist
        return best

    def _grasp(self, name: str) -> None:
        """Remember the object's pose relative to the TCP; it then follows the TCP rigidly."""
        mj, d = self.mj, self.d
        R = d.site_xmat[self.tcp].reshape(3, 3)
        b = self.obj_body[name]
        rel_p = R.T @ (d.xpos[b] - d.site_xpos[self.tcp])
        q_site = np.zeros(4)
        mj.mju_mat2Quat(q_site, d.site_xmat[self.tcp])
        q_inv, rel_q = np.zeros(4), np.zeros(4)
        mj.mju_negQuat(q_inv, q_site)
        mj.mju_mulQuat(rel_q, q_inv, d.xquat[b])
        self.holding, self._rel = name, (rel_p, rel_q)

    def _carry(self) -> None:
        mj, d = self.mj, self.d
        mj.mj_kinematics(self.m, d)
        R = d.site_xmat[self.tcp].reshape(3, 3)
        q_site, q_obj = np.zeros(4), np.zeros(4)
        mj.mju_mat2Quat(q_site, d.site_xmat[self.tcp])
        mj.mju_mulQuat(q_obj, q_site, self._rel[1])
        a, v = self.obj_qadr[self.holding], self.obj_dadr[self.holding]
        d.qpos[a:a + 3] = d.site_xpos[self.tcp] + R @ self._rel[0]
        d.qpos[a + 3:a + 7] = q_obj
        d.qvel[v:v + 6] = 0.0

    # ------------------------------------------------------------------ frames
    def _project_labels(self):
        out = []
        for text, (x0, y0, x1, y1) in _label_rects():
            uv, _ = self.camera.project(np.array([[x0, y0, 0], [x1, y0, 0], [x1, y1, 0], [x0, y1, 0]], float))
            out.append((text, (float(uv[:, 0].min()), float(uv[:, 1].min()),
                               float(uv[:, 0].max()), float(uv[:, 1].max()))))
        return out

    # ------------------------------------------------------------------ async rendering
    def _push_snapshot(self) -> None:
        if getattr(self, "_async", False):
            with self._cond:
                self._snap = self.d.qpos.copy()
                self._snap_seq += 1
                self._cond.notify_all()

    def _render_loop(self) -> None:
        seq = 0
        try:
            while True:
                with self._cond:
                    self._cond.wait_for(lambda: (self._wanted and self._snap_seq > seq) or self._closing, timeout=0.5)
                    if self._closing:
                        break
                    if self._snap_seq == seq or not self._wanted:
                        continue
                    seq, q = self._snap_seq, self._snap
                self._rd.qpos[:] = q
                self.mj.mj_forward(self.m, self._rd)
                pkt = self._render_now(self._rd)
                with self._cond:
                    self._last = pkt
        except Exception as exc:  # noqa: BLE001 - no GL on this machine: keep physics alive, explain
            self.render_error = f"{exc.__class__.__name__}: {exc}"
            log.error("MuJoCo rendering failed (%s). Physics and the policy keep running, but the camera is "
                      "blank. Update your graphics driver, or try: set MUJOCO_GL=egl (Linux)", self.render_error)
        finally:
            if self._renderer is not None:
                try:
                    self._renderer.close()
                except Exception:  # noqa: BLE001
                    pass
                self._renderer = None

    def render(self) -> FramePacket:
        """Newest frame. Async mode: never blocks; returns the previous packet (same frame_id)
        until the render thread finishes a new one. Sync mode: renders here, skipping frames when
        rendering is slow so it uses at most about half the time."""
        if self._async:
            with self._cond:
                if not self._wanted:
                    self._wanted = True
                    self._cond.notify_all()
                last = self._last
            if last is None:  # first frame not ready yet: wait briefly, then a neutral placeholder
                t = time.perf_counter()
                while last is None and time.perf_counter() - t < 10 and not self.render_error:
                    time.sleep(0.01)
                    with self._cond:
                        last = self._last
            return last if last is not None else self._placeholder()
        now = time.perf_counter()
        if self._last is not None and now - self._last_render < 2.0 * self._render_ema - 0.03:
            return self._last
        self._last_render = now
        first = self._renderer is None  # includes one-off OpenGL context creation: not representative
        pkt = self._render_now()
        dt = time.perf_counter() - now
        if not first:
            self._render_ema = dt if self._render_ema == 0 else 0.8 * self._render_ema + 0.2 * dt
        self._last = pkt
        return pkt

    def _placeholder(self) -> FramePacket:
        return FramePacket(frame_id=0, timestamp=time.perf_counter(), rgb=self._bg.copy(), instance_ids=None)

    def _render_now(self, data=None) -> FramePacket:
        mj = self.mj
        data = self.d if data is None else data
        if self._renderer is None:  # create the GL context in the thread that renders
            self._renderer = mj.Renderer(self.m, self.height, self.width)
        r = self._renderer
        r.update_scene(data, camera="main")
        rgb = r.render().copy()
        r.enable_segmentation_rendering()
        r.update_scene(data, camera="main")
        seg = r.render()[:, :, 0].copy()
        r.disable_segmentation_rendering()
        bg = seg < 0
        rgb[bg] = self._bg[bg]  # studio-grey gradient behind the scene, like the reference image
        ids = self.lut[np.clip(seg, -1, len(self.lut) - 2) + 1]
        pts = np.array([data.xpos[b] for b in self.skeleton_bodies] + [data.site_xpos[self.tcp]])
        skel, _ = self.camera.project(pts)
        self.frame_id += 1
        return FramePacket(frame_id=self.frame_id, timestamp=time.perf_counter(), rgb=np.ascontiguousarray(rgb),
                           instance_ids=ids, gt_objects={i: o.name for i, o in enumerate(OBJECTS, start=1)},
                           gt_labels=list(self._labels), robot_skeleton_2d=skel.astype(np.float32))

    def state(self) -> dict:
        objs = {name: self.d.xpos[b].copy() for name, b in self.obj_body.items()}
        return {"ee": self.ee.copy(), "rpy": self.rpy.copy(), "gripper": self.gripper, "holding": self.holding,
                "objects": objs}
