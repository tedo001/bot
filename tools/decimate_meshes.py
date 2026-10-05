"""Build low-poly, smooth-shaded visual meshes ("visual_fast") from the Yaskawa CAD meshes.

The vendor visual STLs total ~77k triangles for a GP7, which costs ~100 ms per frame in
PyBullet's CPU renderer. Quadric decimation to ~15% keeps the silhouette and surface
detail that matter at camera distance and renders faster. Output is OBJ with per-vertex
normals: STL only stores face normals, so a decimated STL renders visibly faceted. GPU (EGL)
rendering can use the full meshes; see AppConfig.sim_mesh_detail.

Dev-time only: pip install fast-simplification numpy-stl
Usage: python tools/decimate_meshes.py [--ratio 0.3]
"""

import argparse
from pathlib import Path

import fast_simplification
import numpy as np
from stl import mesh as stl_mesh

ASSETS = Path(__file__).resolve().parent.parent / "vla_dashboard" / "assets" / "motoman"


def _write_obj(path: Path, verts: np.ndarray, faces: np.ndarray, crease_deg: float = 50.0) -> None:
    """OBJ with smooth normals, split at sharp creases so machined edges stay crisp."""
    tri = verts[faces]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])  # area-weighted face normals
    unit = fn / np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    vn = np.zeros_like(verts)
    np.add.at(vn, faces.ravel(), np.repeat(fn, 3, axis=0))
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
    cos_crease = np.cos(np.radians(crease_deg))
    normals, idx = [], []
    for f in range(len(faces)):  # per corner: smooth normal unless it deviates past the crease angle
        row = []
        for c in range(3):
            n = vn[faces[f, c]]
            if np.dot(n, unit[f]) < cos_crease:
                n = unit[f]
            normals.append(n)
            row.append(len(normals))
        idx.append(row)
    with open(path, "w") as fh:
        fh.write("# decimated from Yaskawa CAD (ROS-Industrial motoman, BSD-3-Clause)\n")
        fh.writelines(f"v {x:.6f} {y:.6f} {z:.6f}\n" for x, y, z in verts)
        fh.writelines(f"vn {x:.4f} {y:.4f} {z:.4f}\n" for x, y, z in normals)
        fh.writelines(f"f {a+1}//{na} {b+1}//{nb} {c+1}//{nc}\n"
                      for (a, b, c), (na, nb, nc) in zip(faces, idx))


def decimate(src: Path, dst: Path, keep: float) -> tuple[int, int]:
    tris = stl_mesh.Mesh.from_file(str(src)).vectors.reshape(-1, 3)
    verts, inv = np.unique(np.round(tris, 6), axis=0, return_inverse=True)  # weld the triangle soup
    faces = inv.reshape(-1, 3)
    faces = faces[(faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])]
    v2, f2 = fast_simplification.simplify(verts.astype(np.float32), faces.astype(np.int64), 1.0 - keep)
    dst.parent.mkdir(parents=True, exist_ok=True)
    _write_obj(dst, v2.astype(np.float64), f2)
    return len(faces), len(f2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ratio", type=float, default=0.3, help="fraction of triangles to keep")
    args = ap.parse_args()
    for model_dir in sorted(p for p in ASSETS.iterdir() if p.is_dir()):
        for src in sorted((model_dir / "visual").glob("*.stl")):
            before, after = decimate(src, model_dir / "visual_fast" / (src.stem + ".obj"), args.ratio)
            print(f"{model_dir.name}/{src.name}: {before} -> {after} triangles")


if __name__ == "__main__":
    main()
