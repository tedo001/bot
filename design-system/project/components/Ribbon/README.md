# Ribbon

The top of every screen: product name, workspace tabs, the active workspace's tools in labelled groups, and on the right the compact E-STOP with the run status.

**Consumer provides:** `tabs` (Workcell, Program, Run, Safety, Train, Diagnostics), `active` + `onTabChange`, `groups` of `tools` (`icon`, `label`, `primary`, `danger`, `disabled`), `meta` (cell file name), and `right` holding `EStop compact` and `StatusPill`.

- The right slot is fixed: E-STOP and status never scroll away or collapse.
- Tools are verbs with 20px icons; at most one `primary` tool per group.
