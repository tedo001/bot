"""URDF for Yaskawa Motoman GP7 / GP8 + a simple parallel-jaw gripper.

Kinematics and meshes come from ROS-Industrial ``motoman`` (``motoman_gp7_support``,
``motoman_gp8_support``; BSD-3-Clause, meshes from Yaskawa CAD). The xacro macros are
expanded here in Python so no ROS install is needed. Mesh paths are written as
absolute paths, so the URDF can live in a temp dir while the meshes stay in the package.
"""

from __future__ import annotations

import math
import tempfile
from dataclasses import dataclass
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "motoman"
YASKAWA_BLUE = (33 / 255, 38 / 255, 191 / 255, 1.0)  # motoman_resources/urdf/common_colors.xacro


@dataclass(frozen=True)
class MotomanSpec:
    name: str
    upper_arm: float  # joint_2_l -> joint_3_u (z)
    forearm: float  # joint_3_u -> joint_4_r (x)
    # (lower, upper) limits in degrees for joints 1..6, from the vendor xacro
    limits: tuple[tuple[float, float], ...] = ((-170, 170), (-65, 145), (-70, 190), (-190, 190), (-135, 135),
                                               (-360, 360))

    @property
    def reach(self) -> float:
        return 0.040 + self.upper_arm + math.hypot(self.forearm, 0.040) + 0.080


SPECS = {
    "gp7": MotomanSpec("gp7", upper_arm=0.445, forearm=0.440),
    "gp8": MotomanSpec("gp8", upper_arm=0.345, forearm=0.340),
}

# Gripper geometry (metres). TCP = point between the fingertips.
GRIPPER_PALM_LEN = 0.06
FINGER_LEN = 0.065
TCP_OFFSET = 0.015 + GRIPPER_PALM_LEN + FINGER_LEN  # tool0 -> fingertips
# Frame-only links still get a tiny inertia so PyBullet doesn't warn about them.
_EMPTY_INERTIA = ('<inertial><mass value="0.001"/>'
                  '<inertia ixx="1e-6" iyy="1e-6" izz="1e-6" ixy="0" ixz="0" iyz="0"/></inertial>')
FINGER_TRAVEL = 0.035  # per finger, fully open


def _mesh_link(spec: MotomanSpec, link: str, visual_dir: str) -> str:
    ext = "obj" if visual_dir == "visual_fast" else "stl"
    vis = ASSETS / spec.name / visual_dir / f"{spec.name}_{link}.{ext}"
    col = ASSETS / spec.name / "collision" / f"{spec.name}_{link}.stl"
    r, g, b, a = YASKAWA_BLUE
    return f"""
  <link name="{link}">
    <visual><geometry><mesh filename="{vis}"/></geometry>
      <material name="yaskawa_blue"><color rgba="{r:.4f} {g:.4f} {b:.4f} {a}"/></material></visual>
    <collision><geometry><mesh filename="{col}"/></geometry></collision>
    <inertial><mass value="2.0"/><inertia ixx="0.01" iyy="0.01" izz="0.01" ixy="0" ixz="0" iyz="0"/></inertial>
  </link>"""


def _box_link(name: str, size, xyz, rgba, mass=0.1) -> str:
    sx, sy, sz = size
    return f"""
  <link name="{name}">
    <visual><origin xyz="{xyz[0]} {xyz[1]} {xyz[2]}"/><geometry><box size="{sx} {sy} {sz}"/></geometry>
      <material name="{name}_mat"><color rgba="{rgba[0]} {rgba[1]} {rgba[2]} {rgba[3]}"/></material></visual>
    <collision><origin xyz="{xyz[0]} {xyz[1]} {xyz[2]}"/><geometry><box size="{sx} {sy} {sz}"/></geometry></collision>
    <inertial><mass value="{mass}"/><inertia ixx="1e-4" iyy="1e-4" izz="1e-4" ixy="0" ixz="0" iyz="0"/></inertial>
  </link>"""


def build_urdf(model: str = "gp7", detail: str = "fast") -> str:
    """``detail="full"``: vendor CAD meshes (best with GPU/EGL rendering).
    ``detail="fast"``: decimated, smooth-shaded OBJ meshes from tools/decimate_meshes.py."""
    spec = SPECS[model]
    visual_dir = "visual_fast" if detail == "fast" else "visual"
    if not (ASSETS / spec.name / visual_dir).is_dir():
        raise FileNotFoundError(f"Motoman meshes missing under {ASSETS / spec.name / visual_dir}")
    lim = [(math.radians(lo), math.radians(hi)) for lo, hi in spec.limits]
    joints = [
        ("joint_1_s", "base_link", "link_1_s", "0 0 0.330", "0 0 1"),
        ("joint_2_l", "link_1_s", "link_2_l", "0.040 0 0", "0 1 0"),
        ("joint_3_u", "link_2_l", "link_3_u", f"0 0 {spec.upper_arm}", "0 -1 0"),
        ("joint_4_r", "link_3_u", "link_4_r", f"{spec.forearm} 0 0.040", "-1 0 0"),
        ("joint_5_b", "link_4_r", "link_5_b", "0 0 0", "0 -1 0"),
        ("joint_6_t", "link_5_b", "link_6_t", "0 0 0", "-1 0 0"),
    ]
    links = "".join(_mesh_link(spec, n, visual_dir) for n in
                    ("base_link", "link_1_s", "link_2_l", "link_3_u", "link_4_r", "link_5_b", "link_6_t"))
    jx = "".join(f"""
  <joint name="{n}" type="revolute"><parent link="{p}"/><child link="{c}"/>
    <origin xyz="{o}" rpy="0 0 0"/><axis xyz="{a}"/>
    <limit lower="{lo:.5f}" upper="{hi:.5f}" effort="100" velocity="6"/></joint>"""
                 for (n, p, c, o, a), (lo, hi) in zip(joints, lim))

    grey, dark = (0.82, 0.82, 0.80, 1), (0.35, 0.35, 0.37, 1)
    gripper = (
        _box_link("adapter", (0.05, 0.05, 0.015), (0, 0, 0.0075), dark)
        + _box_link("palm", (0.05, 0.10, GRIPPER_PALM_LEN), (0, 0, 0.015 + GRIPPER_PALM_LEN / 2), grey)
        + _box_link("finger_left", (0.02, 0.012, FINGER_LEN), (0, 0, FINGER_LEN / 2), grey, 0.02)
        + _box_link("finger_right", (0.02, 0.012, FINGER_LEN), (0, 0, FINGER_LEN / 2), grey, 0.02)
        + f"""
  <link name="tcp">{_EMPTY_INERTIA}</link>"""
    )
    palm_top = 0.015 + GRIPPER_PALM_LEN
    gj = f"""
  <link name="flange">{_EMPTY_INERTIA}</link>
  <joint name="joint_6_t-flange" type="fixed"><parent link="link_6_t"/><child link="flange"/>
    <origin xyz="0.080 0 0" rpy="0 0 0"/></joint>
  <link name="tool0">{_EMPTY_INERTIA}</link>
  <joint name="flange-tool0" type="fixed"><parent link="flange"/><child link="tool0"/>
    <origin xyz="0 0 0" rpy="{math.pi} {-math.pi / 2} 0"/></joint>
  <joint name="tool0-adapter" type="fixed"><parent link="tool0"/><child link="adapter"/>
    <origin xyz="0 0 0"/></joint>
  <joint name="adapter-palm" type="fixed"><parent link="adapter"/><child link="palm"/><origin xyz="0 0 0"/></joint>
  <joint name="finger_left_joint" type="prismatic"><parent link="palm"/><child link="finger_left"/>
    <origin xyz="0 0.006 {palm_top}"/><axis xyz="0 1 0"/>
    <limit lower="0" upper="{FINGER_TRAVEL}" effort="20" velocity="0.2"/></joint>
  <joint name="finger_right_joint" type="prismatic"><parent link="palm"/><child link="finger_right"/>
    <origin xyz="0 -0.006 {palm_top}"/><axis xyz="0 -1 0"/>
    <limit lower="0" upper="{FINGER_TRAVEL}" effort="20" velocity="0.2"/></joint>
  <joint name="palm-tcp" type="fixed"><parent link="palm"/><child link="tcp"/>
    <origin xyz="0 0 {TCP_OFFSET}"/></joint>"""

    urdf = f'<?xml version="1.0"?>\n<robot name="motoman_{spec.name}">{links}{jx}{gripper}{gj}\n</robot>\n'
    out = Path(tempfile.gettempdir()) / f"vla_dashboard_motoman_{spec.name}_{detail}.urdf"
    out.write_text(urdf, encoding="utf-8")
    return str(out)
