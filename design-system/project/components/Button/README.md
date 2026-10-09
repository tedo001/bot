# Button

A command. Primary (`drive` fill) is the one action a region exists for, like "Run simulation" or "Train new model"; secondary is everything else; quiet sits in toolbars; danger is for destructive commands.

**Consumer provides:** a verb label in sentence case (`children`), `onClick`, optional `icon`, `size` (`sm` 24px in dense panels, `md` 32px default, `lg` 40px for run controls) and `kbd` for its shortcut.

- One primary per region at most.
- Disabled buttons keep their place and say why in `title` ("Models still loading").
- Danger is outlined, never filled red: filled red belongs to the E-STOP.
