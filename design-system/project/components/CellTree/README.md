# CellTree

The cell browser: everything in the workcell as a tree. Controller and robot, tool and user frames, gripper, objects, cameras, fixtures.

**Consumer provides:** `nodes` (`id`, `label`, `icon`, `meta`, `badge` `src`/`dst`, `hidden`, `locked`, `children`), `selected` + `onSelect` wired to the viewport selection and the `PropertyInspector`.

- Selecting in the tree selects in the viewport and vice versa.
- Objects the policy chose carry the SRC/DST tag while a plan exists.
