# Yaskawa Motoman GP7 / GP8 meshes

* `gp7/visual`, `gp7/collision`, `gp8/visual`, `gp8/collision`: unmodified STL meshes from
  [ros-industrial/motoman](https://github.com/ros-industrial/motoman)
  (`motoman_gp7_support`, `motoman_gp8_support`, commit `846fbbc5`), licensed **BSD-3-Clause**
  per each package's `package.xml`. Copyright the ROS-Industrial / Yaskawa Motoman contributors.
* `*/visual_fast/*.obj`: derived from the visual STLs by `tools/decimate_meshes.py`
  (quadric decimation to 30 % of the triangles, smooth vertex normals). Same licence.

Joint origins, axes and limits in `vla_dashboard/sim/motoman_urdf.py` are transcribed from
the packages' `gp7_macro.xacro` / `gp8_macro.xacro`.

"Yaskawa" and "Motoman" are trademarks of Yaskawa Electric Corporation. This project is
not affiliated with or endorsed by Yaskawa.
