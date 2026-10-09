/* @ds-bundle: {"format":4,"namespace":"VLAStudio","components":[{"name":"Icon"},{"name":"Button"},{"name":"Segmented"},{"name":"Toggle"},{"name":"RunControls"},{"name":"StatusPill"},{"name":"EStop"},{"name":"Banner"},{"name":"SafetyChecks"},{"name":"InstructionBox"},{"name":"TaskPlan"},{"name":"ProgramList"},{"name":"JogPanel"},{"name":"PoseReadout"},{"name":"CellTree"},{"name":"PropertyInspector"},{"name":"Viewport"},{"name":"Telemetry"},{"name":"Console"},{"name":"TrainingProgress"},{"name":"ModelRegistry"},{"name":"Ribbon"},{"name":"Panel"},{"name":"StatusBar"}]} */
(function () {
  'use strict';
  var R = window.React;
  var h = R.createElement, useState = R.useState, useEffect = R.useEffect, Fragment = R.Fragment;

  var ICONS = {"play":"M7 4.5l12 7.5-12 7.5z","pause":"M8 5v14M16 5v14","stop":"M6 6h12v12H6z","step":"M5 5l9 7-9 7zM18 5v14","reset":"M4.5 12a7.5 7.5 0 1 0 2.2-5.3M4 3.5V8h4.5","home":"M3.5 11.5L12 4l8.5 7.5M6 10v10h12V10M10 20v-5h4v5","estop":"M8.3 3h7.4L21 8.3v7.4L15.7 21H8.3L3 15.7V8.3zM8 12h8","robot":"M4 21h10M6 21v-2.5h6V21M9 18.5L7 11M7 11l7.5-4M14.5 7l3.5 3.5M18 10.5l2.5-1M18 10.5l1 2.5M8.6 11a1.6 1.6 0 1 1 -3.2 0a1.6 1.6 0 1 1 3.2 0M16.1 7a1.6 1.6 0 1 1 -3.2 0a1.6 1.6 0 1 1 3.2 0","gripper":"M12 2.5V7M6 7h12M7 7v6l3 4v4.5M17 7v6l-3 4v4.5","jog":"M12 3v18M3 12h18M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3","axes":"M5 19V5M5 19h14M5 19l8-8M3 7l2-2 2 2M17 17l2 2-2 2","cube":"M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5","target":"M20 12a8 8 0 1 1 -16 0a8 8 0 1 1 16 0M15 12a3 3 0 1 1 -6 0a3 3 0 1 1 6 0M12 1.5V5M12 19v3.5M1.5 12H5M19 12h3.5","camera":"M3 8h4l2-3h6l2 3h4v11H3zM15.5 13a3.5 3.5 0 1 1 -7.0 0a3.5 3.5 0 1 1 7.0 0","eye":"M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12zM14.75 12a2.75 2.75 0 1 1 -5.5 0a2.75 2.75 0 1 1 5.5 0","layers":"M12 3l9 5-9 5-9-5zM3 12.5l9 5 9-5M3 16.5l9 5 9-5","program":"M9 6h11M9 12h11M9 18h11M4 6h1.5M4 12h1.5M4 18h1.5","shield":"M12 3l7.5 3v6c0 4.6-3.2 7.7-7.5 9-4.3-1.3-7.5-4.4-7.5-9V6zM8.5 12l2.5 2.5 4.5-5","policy":"M8 6a2 2 0 1 1 -4 0a2 2 0 1 1 4 0M20 6a2 2 0 1 1 -4 0a2 2 0 1 1 4 0M14 12a2 2 0 1 1 -4 0a2 2 0 1 1 4 0M8 18a2 2 0 1 1 -4 0a2 2 0 1 1 4 0M20 18a2 2 0 1 1 -4 0a2 2 0 1 1 4 0M7.5 7.5l3 3M16.5 7.5l-3 3M7.5 16.5l3-3M16.5 16.5l-3-3","train":"M3 17l5.5-5.5 4 4L21 7M15 7h6v6","chart":"M4 4v16h16M7.5 15l3.5-4.5 3 3 5-6.5","terminal":"M3 4.5h18v15H3zM7 9l3 3-3 3M12.5 15H17","sliders":"M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1M17 6a2 2 0 1 1 -4 0a2 2 0 1 1 4 0M11 12a2 2 0 1 1 -4 0a2 2 0 1 1 4 0M19 18a2 2 0 1 1 -4 0a2 2 0 1 1 4 0","warning":"M12 3.5l9.5 17h-19zM12 10v4.5M12 17.5v.5","check":"M4.5 12.5l5 5 10-11","lock":"M5.5 11h13v10h-13zM8 11V7.5a4 4 0 0 1 8 0V11","chevron":"M9 5.5l6.5 6.5L9 18.5"};

  function cx() {
    var out = [];
    for (var i = 0; i < arguments.length; i++) if (arguments[i]) out.push(arguments[i]);
    return out.join(' ');
  }
  function omit(obj, keys) {
    var out = {};
    for (var k in obj) if (Object.prototype.hasOwnProperty.call(obj, k) && keys.indexOf(k) < 0) out[k] = obj[k];
    return out;
  }
  function useControlled(value, initial, onChange) {
    var st = useState(initial);
    var controlled = value !== undefined;
    return [controlled ? value : st[0], function (next) {
      if (!controlled) st[1](next);
      if (onChange) onChange(next);
    }];
  }
  function signed(v, digits) {
    var s = Math.abs(v).toFixed(digits);
    return (v < 0 ? '−' : '+') + s;
  }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  /* ---------------------------------------------------------------- Foundations */
  function Icon(p) {
    var size = p.size || 16;
    return h('svg', {
      className: cx('vs-icon', p.className), width: size, height: size, viewBox: '0 0 24 24', fill: 'none',
      stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round', strokeLinejoin: 'round',
      role: p.label ? 'img' : undefined, 'aria-label': p.label, 'aria-hidden': p.label ? undefined : 'true',
      style: p.style
    }, h('path', { d: ICONS[p.name] || '' }));
  }

  /* ---------------------------------------------------------------- Actions */
  function Button(p) {
    var variant = p.variant || 'secondary', size = p.size || 'md';
    var rest = omit(p, ['variant', 'size', 'icon', 'kbd', 'className', 'children']);
    return h('button', Object.assign({ type: 'button' }, rest, {
      className: cx('vs-btn', 'vs-btn--' + variant, 'vs-btn--' + size, !p.children && 'vs-btn--icon', p.className)
    }),
      p.icon ? h(Icon, { name: p.icon, size: size === 'lg' ? 18 : 16 }) : null,
      p.children ? h('span', { className: 'vs-btn__label' }, p.children) : null,
      p.kbd ? h('kbd', { className: 'vs-kbd' }, p.kbd) : null);
  }

  function Segmented(p) {
    var opts = (p.options || []).map(function (o) { return typeof o === 'string' ? { value: o, label: o } : o; });
    var c = useControlled(p.value, p.defaultValue !== undefined ? p.defaultValue : (opts[0] && opts[0].value), p.onChange);
    return h('div', { className: cx('vs-seg', p.size === 'sm' && 'vs-seg--sm', p.className), role: 'radiogroup', 'aria-label': p.label },
      opts.map(function (o) {
        var on = o.value === c[0];
        return h('button', {
          key: o.value, type: 'button', role: 'radio', 'aria-checked': on, disabled: p.disabled || o.disabled,
          className: cx('vs-seg__opt', on && 'is-on'), onClick: function () { c[1](o.value); }
        }, o.icon ? h(Icon, { name: o.icon, size: 14 }) : null, o.label);
      }));
  }

  function Toggle(p) {
    var c = useControlled(p.checked, !!p.defaultChecked, p.onChange);
    return h('label', { className: cx('vs-toggle', p.disabled && 'is-disabled', p.className) },
      h('input', {
        type: 'checkbox', role: 'switch', checked: c[0], disabled: p.disabled,
        onChange: function (e) { c[1](e.target.checked); }
      }),
      h('span', { className: 'vs-toggle__track', 'aria-hidden': 'true' }, h('span', { className: 'vs-toggle__thumb' })),
      h('span', { className: 'vs-toggle__text' },
        h('span', { className: 'vs-toggle__label' }, p.label),
        p.hint ? h('span', { className: 'vs-toggle__hint' }, p.hint) : null));
  }

  /* ---------------------------------------------------------------- Status & safety */
  var STATUS = {
    idle: { tone: 'neutral' }, loading: { tone: 'busy', spin: true }, running: { tone: 'drive', icon: 'play' },
    succeeded: { tone: 'ok', icon: 'check' }, stopped: { tone: 'stopped', icon: 'stop' },
    safety_hold: { tone: 'hold', icon: 'warning' }, failed: { tone: 'danger', icon: 'estop' }
  };
  function StatusPill(p) {
    var s = STATUS[p.status] ? p.status : 'idle', m = STATUS[s], lg = p.size === 'lg';
    return h('span', { className: cx('vs-pill', 'vs-pill--' + m.tone, lg && 'vs-pill--lg', p.className), role: 'status' },
      m.spin ? h('span', { className: 'vs-spin', 'aria-hidden': 'true' })
        : m.icon ? h(Icon, { name: m.icon, size: lg ? 16 : 14 }) : h('span', { className: 'vs-pill__dot', 'aria-hidden': 'true' }),
      h('span', null, p.label || s.replace('_', ' ').toUpperCase()));
  }

  function EStop(p) {
    var c = useControlled(p.engaged, !!p.defaultEngaged, p.onChange);
    var on = c[0];
    useEffect(function () {
      if (p.hotkey === false) return undefined;
      function key(e) { if (e.key === 'Escape') { e.preventDefault(); c[1](!on); } }
      window.addEventListener('keydown', key);
      return function () { window.removeEventListener('keydown', key); };
    });
    return h('div', { className: cx('vs-estop', on && 'is-engaged', p.compact && 'vs-estop--compact', p.className) },
      h('button', {
        type: 'button', className: 'vs-estop__btn', 'aria-pressed': on,
        'aria-label': on ? 'E-STOP engaged. Release' : 'E-STOP: hold all motion', title: 'E-STOP (Esc)',
        onClick: function () { c[1](!on); }
      }, h('span', { className: 'vs-estop__label' }, 'E-STOP')),
      p.compact ? null : h('div', { className: 'vs-estop__meta' },
        h('span', { className: 'vs-estop__state' }, on ? 'ALL MOTION HELD' : 'ARMED'),
        h('span', { className: 'vs-estop__hint' }, on ? 'Click or Esc to release' : 'Click or Esc to stop')));
  }

  function Banner(p) {
    var kind = p.kind || 'info';
    var icon = kind === 'estop' ? 'estop' : kind === 'hold' ? 'warning' : 'chart';
    return h('div', { className: cx('vs-banner', 'vs-banner--' + kind, p.className), role: kind === 'info' ? 'status' : 'alert' },
      h(Icon, { name: p.icon || icon, size: 20 }),
      h('div', { className: 'vs-banner__text' },
        h('strong', { className: 'vs-banner__title' }, p.title),
        p.message ? h('span', { className: 'vs-banner__msg' }, p.message) : null),
      p.action ? h('button', { type: 'button', className: 'vs-banner__action', onClick: p.action.onClick }, p.action.label) : null);
  }

  var CHECK_STATE = { ok: ['OK', 'check'], changed: ['CHANGED', 'warning'], fault: ['FAULT', 'estop'] };
  function SafetyChecks(p) {
    var checks = p.checks || [];
    return h('ol', { className: cx('vs-checks', p.className) }, checks.map(function (c, i) {
      var st = CHECK_STATE[c.state] || CHECK_STATE.ok;
      return h('li', { key: c.name, className: cx('vs-checks__row', 'is-' + (c.state || 'ok'), p.selected === i && 'is-selected'),
        onClick: p.onSelect ? function () { p.onSelect(i); } : undefined },
        h('span', { className: 'vs-checks__n' }, i + 1),
        h('span', { className: 'vs-checks__body' },
          h('span', { className: 'vs-checks__name' }, c.name),
          c.detail ? h('span', { className: 'vs-checks__detail' }, c.detail) : null),
        c.value ? h('span', { className: 'vs-checks__value' }, c.value) : h('span'),
        h('span', { className: 'vs-checks__state' }, h(Icon, { name: st[1], size: 14 }), st[0]));
    }));
  }

  /* ---------------------------------------------------------------- Run */
  function RunControls(p) {
    var s = p.status || 'idle';
    var ready = s === 'idle' || s === 'succeeded' || s === 'failed' || s === 'stopped';
    var moving = s === 'running', held = s === 'safety_hold';
    var reason = p.disabledReason || (s === 'loading' ? 'Models still loading' : null);
    function tool(icon, label, enabled, handler, title) {
      return h('button', { type: 'button', className: 'vs-run__tool', disabled: !enabled, onClick: handler, title: title || label }, h(Icon, { name: icon, size: 18 }), h('span', null, label));
    }
    return h('div', { className: cx('vs-run', p.className) },
      h(Button, { variant: 'primary', size: 'lg', icon: 'play', disabled: !ready || !!p.disabledReason, onClick: p.onRun, kbd: 'Ctrl+\u21b5', title: reason || 'Run simulation' }, 'Run simulation'),
      h('div', { className: 'vs-run__tools' },
        tool('step', 'Step', ready && !p.disabledReason, p.onStep, 'Step one action chunk (F5)'),
        tool('pause', 'Pause', moving, p.onPause),
        tool('stop', 'Stop', moving || held, p.onStop, 'Stop episode'),
        tool('reset', 'Reset', ready, p.onReset, 'Reset scene: new random layout')),
      reason ? h('p', { className: 'vs-run__reason' }, h(Icon, { name: s === 'loading' ? 'policy' : 'lock', size: 14 }), reason) : null);
  }

  /* ---------------------------------------------------------------- Program */
  function validateInstruction(text) {
    var t = (text || '').trim();
    if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(t)) return 'Remove control characters from the instruction.';
    if (t.length < 3) return 'Write at least 3 characters, e.g. "Pick up the green ball".';
    if (t.length > 512) return 'Keep the instruction under 512 characters.';
    if (!/[A-Za-z]/.test(t)) return 'The instruction needs words, not only numbers or symbols.';
    return null;
  }
  function InstructionBox(p) {
    var c = useControlled(p.value, p.defaultValue || '', p.onChange);
    var touched = useState(false);
    var err = p.error || (touched[0] ? validateInstruction(c[0]) : null);
    function run() { touched[1](true); if (!validateInstruction(c[0]) && p.onRun) p.onRun(c[0].trim()); }
    return h('div', { className: cx('vs-instr', err && 'is-invalid', p.className) },
      h('label', { className: 'vs-field-label', htmlFor: 'vs-instr-text' }, 'Natural-language instruction'),
      h('textarea', {
        id: 'vs-instr-text', className: 'vs-instr__text', rows: p.rows || 2, value: c[0], disabled: p.disabled,
        placeholder: 'e.g. Put the red cube on the blue cylinder', 'aria-invalid': !!err,
        onChange: function (e) { touched[1](true); c[1](e.target.value); },
        onKeyDown: function (e) { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); run(); } }
      }),
      h('div', { className: 'vs-instr__meta' },
        err ? h('span', { className: 'vs-instr__err', role: 'alert' }, h(Icon, { name: 'warning', size: 14 }), err)
          : h('span', { className: 'vs-instr__hint' }, 'Ctrl+Enter runs · the policy grounds it on what the camera sees'),
        h('span', { className: 'vs-instr__count' }, (c[0] || '').trim().length + '/512')),
      p.examples && p.examples.length ? h('div', { className: 'vs-instr__examples' },
        h('span', { className: 'vs-instr__ex-label' }, 'Examples'),
        p.examples.map(function (ex) {
          return h('button', { key: ex, type: 'button', className: 'vs-chip', onClick: function () { touched[1](false); c[1](ex); } }, ex);
        })) : null);
  }

  function Mark(p) { return h('span', { className: 'vs-tag vs-tag--' + p.kind }, p.kind.toUpperCase()); }

  function TaskPlan(p) {
    var phases = p.phases || [], cur = p.current === undefined ? -1 : p.current, st = p.status || 'running';
    return h('div', { className: cx('vs-plan', p.className) },
      h('div', { className: 'vs-plan__targets' },
        h('div', { className: 'vs-plan__target' }, h(Mark, { kind: 'src' }), h('span', null, p.source || '—')),
        h(Icon, { name: 'chevron', size: 14, className: 'vs-plan__arrow' }),
        h('div', { className: 'vs-plan__target' }, h(Mark, { kind: 'dst' }), h('span', null, p.destination || '—'))),
      p.doneProb !== undefined ? h('div', { className: 'vs-plan__done' },
        h('span', { className: 'vs-field-label' }, 'P(done)'),
        h('span', { className: 'vs-meter' }, h('span', { className: 'vs-meter__fill', style: { width: clamp(p.doneProb, 0, 1) * 100 + '%' } })),
        h('span', { className: 'vs-plan__prob' }, p.doneProb.toFixed(2))) : null,
      p.message ? h('p', { className: cx('vs-plan__msg', st === 'failed' && 'is-failed') }, p.message) : null,
      h('ol', { className: 'vs-plan__steps' }, phases.map(function (ph, i) {
        var state = st === 'done' || i < cur ? 'done' : i === cur ? (st === 'failed' ? 'failed' : st === 'hold' ? 'hold' : 'current') : 'pending';
        var icon = { done: 'check', current: 'play', failed: 'estop', hold: 'warning' }[state];
        var name = typeof ph === 'string' ? ph : ph.name, detail = typeof ph === 'string' ? null : ph.detail;
        return h('li', { key: name, className: 'vs-plan__step is-' + state, 'aria-current': state === 'current' ? 'step' : undefined },
          h('span', { className: 'vs-plan__marker' }, icon ? h(Icon, { name: icon, size: 12 }) : null),
          h('span', { className: 'vs-plan__name' }, name),
          detail ? h('span', { className: 'vs-plan__detail' }, detail) : null);
      })));
  }

  function ProgramList(p) {
    var lines = p.lines || [];
    return h('div', { className: cx('vs-prog', p.className) },
      h('div', { className: 'vs-prog__head' },
        h(Icon, { name: 'program', size: 14 }),
        h('span', { className: 'vs-prog__name' }, p.name || 'MAIN'),
        h('span', { className: 'vs-prog__meta' }, lines.length + ' lines'),
        p.status ? h(StatusPill, { status: p.status }) : null),
      p.palette ? h('div', { className: 'vs-prog__palette', role: 'toolbar', 'aria-label': 'Insert instruction' },
        ['MoveJ', 'MoveL', 'Grip', 'Detect', 'Wait', 'If', 'Call', 'Instruction'].map(function (k) {
          return h('button', { key: k, type: 'button', className: 'vs-prog__tile', onClick: p.onInsert ? function () { p.onInsert(k); } : undefined }, k);
        })) : null,
      h('ol', { className: 'vs-prog__lines' }, lines.map(function (ln, i) {
        var l = typeof ln === 'string' ? { text: ln } : ln;
        return h('li', { key: i, className: cx('vs-prog__line', i === p.current && 'is-current', l.kind === 'comment' && 'is-comment', l.kind === 'language' && 'is-language', i === p.selected && 'is-selected'),
          onClick: p.onSelect ? function () { p.onSelect(i); } : undefined },
          h('span', { className: 'vs-prog__n' }, i === p.current ? h(Icon, { name: 'play', size: 10 }) : i + 1),
          l.op ? h('span', { className: 'vs-prog__op' }, l.op) : null,
          h('span', { className: 'vs-prog__text' }, l.text));
      }), h('li', { className: 'vs-prog__line is-end' }, h('span', { className: 'vs-prog__n' }, '[End]'))));
  }

  /* ---------------------------------------------------------------- Robot */
  var GP7_JOINTS = [
    { name: 'S', label: 'J1 S', min: -170, max: 170, value: 0 }, { name: 'L', label: 'J2 L', min: -65, max: 145, value: 12 },
    { name: 'U', label: 'J3 U', min: -70, max: 190, value: -8 }, { name: 'R', label: 'J4 R', min: -190, max: 190, value: 0 },
    { name: 'B', label: 'J5 B', min: -135, max: 135, value: -64 }, { name: 'T', label: 'J6 T', min: -360, max: 360, value: 0 }
  ];
  var CART = [
    { name: 'X', min: -900, max: 900, value: 50, unit: 'mm', axis: 'x' }, { name: 'Y', min: -900, max: 900, value: 550, unit: 'mm', axis: 'y' },
    { name: 'Z', min: -200, max: 1100, value: 300, unit: 'mm', axis: 'z' }, { name: 'W', min: -180, max: 180, value: 180, unit: 'deg', wrap: true },
    { name: 'P', min: -180, max: 180, value: 0, unit: 'deg', wrap: true }, { name: 'R', min: -180, max: 180, value: 90, unit: 'deg', wrap: true }
  ];
  function JogPanel(p) {
    var frameC = useControlled(p.frame, p.defaultFrame || 'joint', p.onFrameChange);
    var frame = frameC[0];
    var axes = frame === 'joint' ? (p.joints || GP7_JOINTS) : (p.cartesian || CART);
    var vals = useState({});
    var dm = useControlled(p.deadman, false, p.onDeadmanChange);
    var speed = useControlled(p.speed, 10, p.onSpeedChange);
    var step = useState(frame === 'joint' ? '1' : '10');
    var locked = p.disabledReason;
    var live = dm[0] && !locked;
    useEffect(function () {
      if (locked) return undefined;
      function down(e) { if (e.code === 'Space' && !e.repeat && e.target === document.body) { e.preventDefault(); dm[1](true); } }
      function up(e) { if (e.code === 'Space') dm[1](false); }
      window.addEventListener('keydown', down); window.addEventListener('keyup', up);
      return function () { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up); };
    });
    function valueOf(a) { var k = frame + a.name; return vals[0][k] !== undefined ? vals[0][k] : a.value; }
    function jog(a, dir) {
      var k = frame + a.name, next = {};
      for (var key in vals[0]) next[key] = vals[0][key];
      next[k] = clamp(valueOf(a) + dir * parseFloat(step[0]), a.min, a.max);
      vals[1](next);
      if (p.onJog) p.onJog({ frame: frame, axis: a.name, value: next[k] });
    }
    var stepOpts = frame === 'joint' ? ['10', '1', '0.1'] : ['100', '10', '1'];
    var stepUnit = frame === 'joint' ? '°' : ' mm';
    return h('div', { className: cx('vs-jog', locked && 'is-locked', p.className) },
      h(Segmented, { label: 'Jog frame', size: 'sm', value: frame, onChange: function (f) { frameC[1](f); step[1](f === 'joint' ? '1' : '10'); },
        options: [{ value: 'joint', label: 'Joint' }, { value: 'world', label: 'World' }, { value: 'tool', label: 'Tool' }, { value: 'user', label: 'User' }] }),
      h('div', { className: 'vs-jog__axes' }, axes.map(function (a) {
        var v = valueOf(a), frac = (v - a.min) / (a.max - a.min), near = !a.wrap && (frac < 0.05 || frac > 0.95);
        var unit = a.unit || 'deg';
        return h('div', { key: a.name, className: cx('vs-jog__axis', near && 'is-near') },
          h('button', { type: 'button', className: 'vs-jog__key', disabled: !live, 'aria-label': a.name + ' minus', onClick: function () { jog(a, -1); } }, '−'),
          h('div', { className: 'vs-jog__mid' },
            h('div', { className: 'vs-jog__top' },
              h('span', { className: cx('vs-jog__name', a.axis && 'vs-axis vs-axis--' + a.axis) }, a.label || a.name),
              h('span', { className: 'vs-jog__val' }, signed(v, unit === 'mm' ? 1 : 1), h('span', { className: 'vs-unit' }, ' ' + unit))),
            h('div', { className: 'vs-jog__bar', title: a.min + ' to ' + a.max + ' ' + unit },
              h('span', { className: 'vs-jog__zero', style: { left: clamp((0 - a.min) / (a.max - a.min), 0, 1) * 100 + '%' } }),
              h('span', { className: 'vs-jog__pos', style: { left: clamp(frac, 0, 1) * 100 + '%' } }))),
          h('button', { type: 'button', className: 'vs-jog__key', disabled: !live, 'aria-label': a.name + ' plus', onClick: function () { jog(a, 1); } }, '+'));
      })),
      h('div', { className: 'vs-jog__settings' },
        h('label', { className: 'vs-jog__speed' },
          h('span', { className: 'vs-field-label' }, 'Speed override'),
          h('input', { type: 'range', min: 1, max: 25, value: speed[0], onChange: function (e) { speed[1](+e.target.value); } }),
          h('span', { className: 'vs-jog__pct' }, speed[0] + '%')),
        h('div', { className: 'vs-jog__step' },
          h('span', { className: 'vs-field-label' }, 'Step'),
          h(Segmented, { label: 'Step size', size: 'sm', value: step[0], onChange: step[1],
            options: stepOpts.map(function (s) { return { value: s, label: s + stepUnit }; }) }))),
      locked ? h('p', { className: 'vs-jog__locked' }, h(Icon, { name: 'lock', size: 14 }), locked)
        : h('button', {
          type: 'button', className: cx('vs-deadman', dm[0] && 'is-held'), 'aria-pressed': dm[0],
          onMouseDown: function () { dm[1](true); }, onMouseUp: function () { dm[1](false); }, onMouseLeave: function () { dm[1](false); },
          onTouchStart: function () { dm[1](true); }, onTouchEnd: function () { dm[1](false); }
        }, dm[0] ? 'Deadman held: jog enabled' : 'Hold to enable jog (Space)'),
      h('div', { className: 'vs-jog__actions' },
        h(Button, { size: 'sm', icon: 'target', onClick: p.onRecord, disabled: !!locked }, 'Record pose'),
        h(Button, { size: 'sm', icon: 'home', onClick: p.onHome, disabled: !!locked }, 'Go home')));
  }

  function PoseReadout(p) {
    var pose = p.pose || {}, g = p.gripper;
    var rows = [['X', pose.x, 'x'], ['Y', pose.y, 'y'], ['Z', pose.z, 'z'], ['W', pose.w], ['P', pose.p], ['R', pose.r]];
    var lin = p.linearUnit || 'm', digits = lin === 'm' ? 3 : 1;
    return h('div', { className: cx('vs-pose', p.className) },
      h('div', { className: 'vs-pose__head' }, h('span', { className: 'vs-field-label' }, 'TCP in ' + (p.frame || 'World')), p.stale ? h('span', { className: 'vs-pose__stale' }, 'stale ' + p.stale) : null),
      h('dl', { className: cx('vs-pose__grid', p.stale && 'is-stale') }, rows.map(function (r, i) {
        return h('div', { key: r[0], className: 'vs-pose__cell' },
          h('dt', { className: cx('vs-pose__k', r[2] && 'vs-axis vs-axis--' + r[2]) }, r[0]),
          h('dd', { className: 'vs-pose__v' }, r[1] === undefined ? '—' : signed(r[1], i < 3 ? digits : 1), h('span', { className: 'vs-unit' }, i < 3 ? ' ' + lin : ' deg')));
      })),
      g ? h('div', { className: 'vs-pose__grip' },
        h(Icon, { name: 'gripper', size: 14 }),
        h('span', { className: 'vs-field-label' }, 'Gripper'),
        h('span', { className: 'vs-meter vs-meter--grip' }, h('span', { className: 'vs-meter__fill', style: { width: clamp(g.opening, 0, 1) * 100 + '%' } })),
        h('span', { className: 'vs-pose__open' }, g.opening.toFixed(2) + ' open'),
        g.holding ? h('span', { className: 'vs-pose__hold' }, 'holding ', h('strong', null, g.holding)) : null) : null);
  }

  /* ---------------------------------------------------------------- Workcell */
  function TreeNode(p) {
    var n = p.node, kids = n.children || [];
    var open = useState(p.defaultOpen !== false && n.open !== false);
    var sel = p.selected === n.id;
    return h('li', { role: 'treeitem', 'aria-expanded': kids.length ? open[0] : undefined, 'aria-selected': sel },
      h('div', { className: cx('vs-tree__row', sel && 'is-selected', n.hidden && 'is-hidden'), style: { paddingLeft: 4 + p.depth * 14 + 'px' },
        onClick: function () { if (p.onSelect) p.onSelect(n.id); } },
        kids.length ? h('button', { type: 'button', className: cx('vs-tree__chev', open[0] && 'is-open'), 'aria-label': open[0] ? 'Collapse' : 'Expand',
          onClick: function (e) { e.stopPropagation(); open[1](!open[0]); } }, h(Icon, { name: 'chevron', size: 12 })) : h('span', { className: 'vs-tree__chev' }),
        n.icon ? h(Icon, { name: n.icon, size: 14, className: 'vs-tree__icon' }) : null,
        h('span', { className: 'vs-tree__label' }, n.label),
        n.meta ? h('span', { className: 'vs-tree__meta' }, n.meta) : null,
        n.badge ? h(Mark, { kind: n.badge }) : null,
        n.locked ? h(Icon, { name: 'lock', size: 12, className: 'vs-tree__flag', label: 'Locked' }) : null,
        n.hidden ? h('span', { className: 'vs-tree__flag' }, 'hidden') : null),
      kids.length && open[0] ? h('ul', { role: 'group' }, kids.map(function (k) {
        return h(TreeNode, { key: k.id, node: k, depth: p.depth + 1, selected: p.selected, onSelect: p.onSelect, defaultOpen: p.defaultOpen });
      })) : null);
  }
  function CellTree(p) {
    var c = useControlled(p.selected, p.defaultSelected, p.onSelect);
    return h('ul', { className: cx('vs-tree', p.className), role: 'tree', 'aria-label': p.label || 'Cell browser' },
      (p.nodes || []).map(function (n) { return h(TreeNode, { key: n.id, node: n, depth: 0, selected: c[0], onSelect: c[1], defaultOpen: p.defaultOpen }); }));
  }

  function PropertyInspector(p) {
    return h('div', { className: cx('vs-props', p.className) },
      p.title ? h('div', { className: 'vs-props__title' }, p.icon ? h(Icon, { name: p.icon, size: 14 }) : null, h('span', null, p.title), p.subtitle ? h('span', { className: 'vs-props__sub' }, p.subtitle) : null) : null,
      (p.sections || []).map(function (s) {
        return h('section', { key: s.title, className: 'vs-props__section' },
          h('h4', { className: 'vs-props__head' }, s.title),
          h('div', { className: 'vs-props__grid', style: { gridTemplateColumns: 'repeat(' + (s.columns || 1) + ', minmax(0, 1fr))' } },
            s.fields.map(function (f) {
              var id = 'vs-p-' + s.title + '-' + f.label;
              var control;
              if (f.kind === 'toggle') control = h(Toggle, { defaultChecked: !!f.value, label: f.label });
              else if (f.kind === 'select') control = h('select', { id: id, className: 'vs-input', defaultValue: f.value }, (f.options || []).map(function (o) { return h('option', { key: o }, o); }));
              else control = h('input', { id: id, className: cx('vs-input', f.kind === 'number' && 'vs-input--num'), defaultValue: f.value, inputMode: f.kind === 'number' ? 'decimal' : undefined });
              return h('div', { key: f.label, className: 'vs-props__field' },
                f.kind === 'toggle' ? null : h('div', { className: 'vs-props__lrow' },
                  h('label', { className: cx('vs-field-label', f.axis && 'vs-axis vs-axis--' + f.axis), htmlFor: id }, f.label),
                  f.unit ? h('span', { className: 'vs-unit' }, f.unit) : null),
                control);
            })));
      }));
  }

  /* Viewport: a schematic of the workcell. Scene colours come from the simulator's render colours, not the UI tokens. */
  var SCENE = { robot: '#2957db', cube: '#db1f1f', cylinder: '#242ed6', sphere: '#29c747' };
  function iso(x, y, z) { return [480 + (x - y) * 0.87 * 260, 300 + (x + y) * 0.5 * 260 - z * 300]; }
  function Viewport(p) {
    var ov = p.overlays || {}, mode = p.mode || '3d', objs = p.objects || [];
    var grid = [];
    for (var i = -6; i <= 6; i++) {
      var a = iso(i * 0.15, -0.9, 0), b = iso(i * 0.15, 0.9, 0), c2 = iso(-0.9, i * 0.15, 0), d = iso(0.9, i * 0.15, 0);
      grid.push(h('line', { key: 'g' + i, x1: a[0], y1: a[1], x2: b[0], y2: b[1], className: 'vs-vp__grid' }));
      grid.push(h('line', { key: 'h' + i, x1: c2[0], y1: c2[1], x2: d[0], y2: d[1], className: 'vs-vp__grid' }));
    }
    var t = [iso(-0.5, 0.15, 0.0), iso(0.5, 0.15, 0.0), iso(0.5, 0.75, 0.0), iso(-0.5, 0.75, 0.0)];
    var table = h('polygon', { points: t.map(function (q) { return q.join(','); }).join(' '), className: 'vs-vp__table' });
    var base = iso(0, -0.25, 0), sh = iso(0, -0.25, 0.33), el = iso(0.02, -0.12, 0.74), tp = p.tcp || [0.05, 0.4, 0.32], wr = iso(tp[0] + 0.05, tp[1] - 0.1, tp[2] + 0.12), tcp = iso(tp[0], tp[1], tp[2]);
    var arm = [base, sh, el, wr, tcp];
    function seg(a2, b2, w, k) { return h('line', { key: k, x1: a2[0], y1: a2[1], x2: b2[0], y2: b2[1], stroke: SCENE.robot, strokeWidth: w, strokeLinecap: 'round' }); }
    var robot = h('g', { className: 'vs-vp__robot' },
      h('ellipse', { cx: base[0], cy: base[1] + 6, rx: 46, ry: 20, className: 'vs-vp__base' }),
      seg(base, sh, 30, 'a'), seg(sh, el, 22, 'b'), seg(el, wr, 16, 'c'), seg(wr, tcp, 10, 'd'),
      h('circle', { cx: sh[0], cy: sh[1], r: 15, fill: SCENE.robot }), h('circle', { cx: el[0], cy: el[1], r: 11, fill: SCENE.robot }),
      h('path', { d: 'M' + (tcp[0] - 8) + ' ' + (tcp[1] + 4) + 'v14M' + (tcp[0] + 8) + ' ' + (tcp[1] + 4) + 'v14', className: 'vs-vp__fingers' }));
    var skeleton = ov.skeleton ? h('g', null,
      h('polyline', { points: arm.map(function (q) { return q.join(','); }).join(' '), className: 'vs-vp__skel' }),
      arm.map(function (q, k) { return h('circle', { key: k, cx: q[0], cy: q[1], r: 5, className: 'vs-vp__joint' }); })) : null;
    var objects = objs.map(function (o) {
      var q = iso(o.x, o.y, 0), col = o.color || SCENE[o.shape] || '#888888', shape;
      if (o.shape === 'sphere') shape = h('circle', { cx: q[0], cy: q[1] - 16, r: 16, fill: col });
      else if (o.shape === 'cylinder') shape = h('g', null, h('rect', { x: q[0] - 15, y: q[1] - 38, width: 30, height: 34, fill: col }), h('ellipse', { cx: q[0], cy: q[1] - 38, rx: 15, ry: 6, fill: col, className: 'vs-vp__lid' }), h('ellipse', { cx: q[0], cy: q[1] - 4, rx: 15, ry: 6, fill: col }));
      else shape = h('g', null, h('polygon', { points: [[q[0], q[1] - 40], [q[0] + 18, q[1] - 30], [q[0] + 18, q[1] - 6], [q[0], q[1] + 4], [q[0] - 18, q[1] - 6], [q[0] - 18, q[1] - 30]].map(function (z) { return z.join(','); }).join(' '), fill: col }), h('polygon', { points: [[q[0], q[1] - 40], [q[0] + 18, q[1] - 30], [q[0], q[1] - 20], [q[0] - 18, q[1] - 30]].map(function (z) { return z.join(','); }).join(' '), className: 'vs-vp__lid', fill: col }));
      var bx = [q[0] - 26, q[1] - 50, 52, 62];
      return h('g', { key: o.id || o.label },
        o.mask && ov.masks ? h('ellipse', { cx: q[0], cy: q[1] - 18, rx: 24, ry: 26, className: 'vs-vp__mask' }) : null,
        shape,
        ov.boxes ? h('g', null, h('rect', { x: bx[0], y: bx[1], width: bx[2], height: bx[3], className: 'vs-vp__box' }),
          h('text', { x: bx[0], y: bx[1] - 5, className: 'vs-vp__boxlabel' }, (o.label || o.shape) + ' ' + (o.score || 0.97).toFixed(2))) : null,
        o.mark ? h('g', null, h('rect', { x: bx[0] - 5, y: bx[1] - 5, width: bx[2] + 10, height: bx[3] + 10, className: 'vs-vp__mark vs-vp__mark--' + o.mark }),
          h('rect', { x: bx[0] - 5, y: bx[1] + bx[3] + 6, width: 30, height: 16, rx: 2, className: 'vs-vp__tagbg vs-vp__tagbg--' + o.mark }),
          h('text', { x: bx[0] + 10, y: bx[1] + bx[3] + 18, className: 'vs-vp__tag' }, o.mark.toUpperCase())) : null,
        ov.ocr && o.label ? h('g', null, h('rect', { x: q[0] - 22, y: q[1] + 40, width: 44, height: 14, className: 'vs-vp__ocr' }),
          h('text', { x: q[0], y: q[1] + 50, className: 'vs-vp__ocrtext' }, o.label.split(' ').pop().toUpperCase())) : null);
    });
    return h('div', { className: cx('vs-vp', 'vs-vp--' + mode, p.className), style: p.height ? { height: p.height } : undefined },
      h('svg', { className: 'vs-vp__scene', viewBox: '0 0 960 560', preserveAspectRatio: 'xMidYMid slice', role: 'img', 'aria-label': p.label || 'Workcell viewport' },
        h('g', null, grid), table, objects, robot, skeleton),
      ov.hud && p.hud ? h('div', { className: 'vs-vp__hud' }, p.hud) : null,
      p.banner ? h('div', { className: 'vs-vp__banner' }, p.banner) : null,
      p.showCube !== false ? h('div', { className: 'vs-vp__cube', 'aria-hidden': 'true' },
        h('svg', { viewBox: '0 0 64 64', width: 64, height: 64 },
          h('polygon', { points: '32,6 56,18 32,30 8,18', className: 'vs-vp__face vs-vp__face--top' }),
          h('polygon', { points: '8,18 32,30 32,58 8,46', className: 'vs-vp__face' }),
          h('polygon', { points: '56,18 32,30 32,58 56,46', className: 'vs-vp__face vs-vp__face--side' }),
          h('text', { x: 32, y: 21, className: 'vs-vp__facetext' }, 'TOP'),
          h('text', { x: 20, y: 42, className: 'vs-vp__facetext' }, 'FRONT'),
          h('text', { x: 44, y: 42, className: 'vs-vp__facetext' }, 'RIGHT'))) : null,
      p.showTriad !== false ? h('div', { className: 'vs-vp__triad', 'aria-hidden': 'true' },
        h('svg', { viewBox: '0 0 56 56', width: 56, height: 56 },
          h('line', { x1: 14, y1: 42, x2: 40, y2: 52, className: 'vs-vp__ax vs-vp__ax--x' }), h('text', { x: 46, y: 54, className: 'vs-vp__axt vs-vp__axt--x' }, 'X'),
          h('line', { x1: 14, y1: 42, x2: 40, y2: 30, className: 'vs-vp__ax vs-vp__ax--y' }), h('text', { x: 46, y: 30, className: 'vs-vp__axt vs-vp__axt--y' }, 'Y'),
          h('line', { x1: 14, y1: 42, x2: 14, y2: 12, className: 'vs-vp__ax vs-vp__ax--z' }), h('text', { x: 10, y: 9, className: 'vs-vp__axt vs-vp__axt--z' }, 'Z'))) : null,
      p.toolbar ? h('div', { className: 'vs-vp__toolbar' }, p.toolbar) : null,
      p.children);
  }

  /* ---------------------------------------------------------------- Data */
  function Telemetry(p) {
    var stages = p.stages || {}, names = Object.keys(stages), budget = p.budgetMs || 50;
    var total = names.reduce(function (s, k) { return s + stages[k]; }, 0), over = total > budget;
    return h('div', { className: cx('vs-telem', p.className) },
      h('div', { className: 'vs-telem__tiles' }, (p.metrics || []).map(function (m) {
        return h('div', { key: m.label, className: cx('vs-telem__tile', m.tone && 'is-' + m.tone) },
          h('span', { className: 'vs-field-label' }, m.label),
          h('span', { className: 'vs-telem__value' }, m.value, m.unit ? h('span', { className: 'vs-unit' }, ' ' + m.unit) : null),
          m.note ? h('span', { className: 'vs-telem__note' }, m.tone === 'hold' ? h(Icon, { name: 'warning', size: 12 }) : null, m.note) : null);
      })),
      names.length ? h('div', { className: 'vs-telem__budget' },
        h('div', { className: 'vs-telem__bhead' },
          h('span', { className: 'vs-field-label' }, 'Control tick'),
          h('span', { className: cx('vs-telem__btotal', over && 'is-over') }, total.toFixed(1) + ' / ' + budget + ' ms')),
        h('div', { className: 'vs-telem__bar' }, names.map(function (k, i) {
          return h('span', { key: k, className: 'vs-telem__seg vs-telem__seg--' + (i % 4), style: { width: Math.min(100, stages[k] / budget * 100) + '%' }, title: k + ' ' + stages[k].toFixed(1) + ' ms' });
        })),
        h('ul', { className: 'vs-telem__legend' }, names.map(function (k, i) {
          return h('li', { key: k }, h('span', { className: 'vs-telem__sw vs-telem__seg--' + (i % 4) }), k, h('span', { className: 'vs-telem__ms' }, stages[k].toFixed(1)));
        }))) : null);
  }

  function Console(p) {
    var f = useControlled(p.filter, 'all', p.onFilterChange);
    var lines = (p.lines || []).filter(function (l) {
      return f[0] === 'all' || (f[0] === 'warn' && (l.level === 'WARN' || l.level === 'ERROR')) || (f[0] === 'error' && l.level === 'ERROR');
    });
    return h('div', { className: cx('vs-console', p.className) },
      h('div', { className: 'vs-console__head' },
        h(Segmented, { label: 'Filter', size: 'sm', value: f[0], onChange: f[1], options: [{ value: 'all', label: 'All' }, { value: 'warn', label: 'Warnings' }, { value: 'error', label: 'Errors' }] }),
        h('span', { className: 'vs-console__count' }, lines.length + ' lines')),
      h('ol', { className: 'vs-console__lines', 'aria-live': 'polite', style: p.height ? { maxHeight: p.height } : undefined }, lines.map(function (l, i) {
        return h('li', { key: i, className: 'vs-console__line is-' + (l.level || 'INFO').toLowerCase() },
          h('span', { className: 'vs-console__t' }, l.t),
          h('span', { className: 'vs-console__lvl' }, l.level || 'INFO'),
          l.src ? h('span', { className: 'vs-console__src' }, l.src + ':') : null,
          h('span', { className: 'vs-console__msg' }, l.msg));
      })));
  }

  /* ---------------------------------------------------------------- Brain */
  var TRAIN_STAGES = [
    { name: 'Teacher demonstrations', detail: 'rule-based planner, random layouts' },
    { name: 'Training epochs', detail: 'behaviour cloning, action chunks' },
    { name: 'Closed-loop evaluation', detail: 'new layouts, both simulators' }
  ];
  function TrainingProgress(p) {
    var st = p.status || 'idle', cur = p.stage === undefined ? -1 : p.stage, stages = p.stages || TRAIN_STAGES;
    var preset = useControlled(p.preset, 'quick', p.onPresetChange);
    var running = st === 'running';
    return h('div', { className: cx('vs-train', p.className) },
      h('div', { className: 'vs-train__row' },
        h(Segmented, { label: 'Preset', size: 'sm', value: preset[0], onChange: preset[1], disabled: running,
          options: [{ value: 'quick', label: 'Quick · 5–10 min' }, { value: 'full', label: 'Full · ~40 min' }] }),
        h('span', { className: 'vs-train__spacer' }),
        h(Button, { variant: 'primary', icon: 'train', disabled: running, onClick: p.onTrain }, 'Train new model'),
        h(Button, { icon: 'stop', disabled: !running, onClick: p.onStop }, 'Stop')),
      h('ol', { className: 'vs-train__stages' }, stages.map(function (s, i) {
        var state = st === 'done' || i < cur ? 'done' : i === cur ? (st === 'failed' ? 'failed' : 'current') : 'pending';
        return h('li', { key: s.name, className: 'vs-train__stage is-' + state },
          h('span', { className: 'vs-train__marker' }, state === 'done' ? h(Icon, { name: 'check', size: 12 }) : state === 'failed' ? h(Icon, { name: 'estop', size: 12 }) : i + 1),
          h('span', { className: 'vs-train__sname' }, s.name),
          h('span', { className: 'vs-train__sdetail' }, s.detail));
      })),
      h('div', { className: cx('vs-progress', st === 'failed' && 'is-failed', st === 'done' && 'is-done'), role: 'progressbar', 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': Math.round((p.progress || 0) * 100) },
        h('span', { className: 'vs-progress__fill', style: { width: clamp(p.progress || 0, 0, 1) * 100 + '%' } })),
      h('p', { className: 'vs-train__msg' }, h('span', { className: 'vs-train__pct' }, Math.round((p.progress || 0) * 100) + '%'), p.message || 'The rule-based teacher generates demonstrations, the network learns from them, is evaluated, and the new model is switched in automatically.'));
  }

  function ModelRegistry(p) {
    var models = p.models || [];
    function pct(v) { return v === undefined || v === null ? '—' : Math.round(v * 100) + '%'; }
    return h('table', { className: cx('vs-models', p.className) },
      h('thead', null, h('tr', null, h('th', null, 'Model'), h('th', { className: 'num' }, 'Sim'), h('th', { className: 'num' }, 'GP7 PyB'), h('th', { className: 'num' }, 'GP7 MuJ'), h('th', null, ''))),
      h('tbody', null, models.map(function (m) {
        return h('tr', { key: m.file, className: cx(m.driving && 'is-driving', p.selected === m.file && 'is-selected'), onClick: p.onSelect ? function () { p.onSelect(m.file); } : undefined },
          h('td', null, h('span', { className: 'vs-models__name' }, m.name), h('span', { className: 'vs-models__file' }, m.file + (m.trained ? ' · ' + m.trained : ''))),
          h('td', { className: 'num' }, pct(m.sim)), h('td', { className: 'num' }, pct(m.pybullet)), h('td', { className: 'num' }, pct(m.mujoco)),
          h('td', { className: 'vs-models__state' }, m.driving ? h('span', { className: 'vs-pill vs-pill--ok' }, h(Icon, { name: 'policy', size: 12 }), 'DRIVING')
            : p.onActivate ? h(Button, { size: 'sm', onClick: function (e) { e.stopPropagation(); p.onActivate(m.file); } }, 'Use') : null));
      })));
  }

  /* ---------------------------------------------------------------- Shell */
  function Ribbon(p) {
    var tab = useControlled(p.active, p.tabs && p.tabs[0] && p.tabs[0].id, p.onTabChange);
    return h('header', { className: cx('vs-ribbon', p.className) },
      h('div', { className: 'vs-ribbon__tabs' },
        h('span', { className: 'vs-ribbon__product' }, p.product || 'VLA Robot Studio'),
        h('nav', { className: 'vs-ribbon__nav', role: 'tablist' }, (p.tabs || []).map(function (t) {
          var on = t.id === tab[0];
          return h('button', { key: t.id, type: 'button', role: 'tab', 'aria-selected': on, className: cx('vs-ribbon__tab', on && 'is-on'), onClick: function () { tab[1](t.id); } },
            t.icon ? h(Icon, { name: t.icon, size: 14 }) : null, t.label);
        })),
        p.meta ? h('span', { className: 'vs-ribbon__meta' }, p.meta) : null),
      h('div', { className: 'vs-ribbon__tools' },
        h('div', { className: 'vs-ribbon__groups' }, (p.groups || []).map(function (g) {
          return h('div', { key: g.label, className: 'vs-ribbon__group' },
            h('div', { className: 'vs-ribbon__items' }, g.tools.map(function (t) {
              return h('button', { key: t.label, type: 'button', className: cx('vs-ribbon__tool', t.primary && 'is-primary', t.danger && 'is-danger'), disabled: t.disabled, title: t.title || t.label, onClick: t.onClick },
                h(Icon, { name: t.icon, size: 20 }), h('span', null, t.label));
            })),
            h('span', { className: 'vs-ribbon__glabel' }, g.label));
        })),
        p.right ? h('div', { className: 'vs-ribbon__right' }, p.right) : null));
  }

  function Panel(p) {
    var open = useState(p.defaultOpen !== false);
    var collapsible = !!p.collapsible;
    return h('section', { className: cx('vs-panel', p.flush && 'vs-panel--flush', p.floating && 'vs-panel--float', p.className), style: p.style },
      h('header', { className: 'vs-panel__head' },
        collapsible ? h('button', { type: 'button', className: cx('vs-panel__chev', open[0] && 'is-open'), 'aria-expanded': open[0], 'aria-label': (open[0] ? 'Collapse ' : 'Expand ') + p.title, onClick: function () { open[1](!open[0]); } }, h(Icon, { name: 'chevron', size: 12 })) : null,
        p.icon ? h(Icon, { name: p.icon, size: 14, className: 'vs-panel__icon' }) : null,
        h('h3', { className: 'vs-panel__title' }, p.title),
        p.meta ? h('span', { className: 'vs-panel__meta' }, p.meta) : null,
        p.actions ? h('div', { className: 'vs-panel__actions' }, p.actions) : null),
      open[0] ? h('div', { className: 'vs-panel__body' }, p.children) : null,
      open[0] && p.footer ? h('footer', { className: 'vs-panel__foot' }, p.footer) : null);
  }

  function StatusBar(p) {
    return h('footer', { className: cx('vs-statusbar', p.className) },
      p.status ? h(StatusPill, { status: p.status }) : null,
      (p.items || []).map(function (it, i) {
        return h('span', { key: i, className: cx('vs-statusbar__item', it.tone && 'is-' + it.tone, it.push && 'is-push') },
          it.icon ? h(Icon, { name: it.icon, size: 12 }) : null,
          it.label ? h('span', { className: 'vs-statusbar__k' }, it.label) : null,
          h('span', { className: 'vs-statusbar__v' }, it.value));
      }));
  }

  var api = {
    Icon: Icon, Button: Button, Segmented: Segmented, Toggle: Toggle, RunControls: RunControls,
    StatusPill: StatusPill, EStop: EStop, Banner: Banner, SafetyChecks: SafetyChecks,
    InstructionBox: InstructionBox, TaskPlan: TaskPlan, ProgramList: ProgramList,
    JogPanel: JogPanel, PoseReadout: PoseReadout,
    CellTree: CellTree, PropertyInspector: PropertyInspector, Viewport: Viewport,
    Telemetry: Telemetry, Console: Console, TrainingProgress: TrainingProgress, ModelRegistry: ModelRegistry,
    Ribbon: Ribbon, Panel: Panel, StatusBar: StatusBar,
    validateInstruction: validateInstruction, ICON_NAMES: Object.keys(ICONS)
  };
  window.VLAStudio = Object.assign(window.VLAStudio || {}, api);
})();
