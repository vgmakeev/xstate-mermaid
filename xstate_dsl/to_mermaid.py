"""Convert XState v5 JSON config dict → Mermaid stateDiagram-v2 text."""
from __future__ import annotations
import json
from typing import Any


def to_mermaid(xstate_config: dict[str, Any]) -> str:
    """Convert XState v5 config dict (or {setup, config} pair) to Mermaid stateDiagram-v2."""
    if "config" in xstate_config and "setup" in xstate_config:
        config = xstate_config["config"]
    else:
        config = xstate_config

    lines: list[str] = ['stateDiagram-v2']
    ind = '    '

    # Machine metadata as %% comments
    lines.append(f'{ind}%% machine: {config.get("id", "unnamed")}')
    if config.get("version"):
        lines.append(f'{ind}%% version: {config["version"]}')
    ctx = config.get("context")
    if ctx:
        _emit_comment_value(lines, ind, "context", ctx)
    inp = config.get("input")
    if inp:
        _emit_comment_value(lines, ind, "input", inp)
    out = config.get("output")
    if out and not config.get("states"):
        _emit_comment_value(lines, ind, "output", out)

    # Wildcard transitions
    on = config.get("on", {})
    if "*" in on:
        for t in _ensure_list(on["*"]):
            lines.append(f'{ind}%% on *: {_format_wildcard(t)}')

    lines.append('')

    # Emit root scope
    states = config.get("states", {})
    initial = config.get("initial")
    _emit_scope(lines, states, initial, indent=1)

    return "\n".join(lines).rstrip() + "\n"


def _emit_scope(lines: list[str], states: dict, initial: str | None, indent: int):
    """Emit [*], transitions, final markers, and state blocks for a scope."""
    ind = '    ' * indent

    if initial:
        lines.append(f'{ind}[*] --> {initial}')

    # Transitions from each state
    for name, cfg in states.items():
        _emit_transitions(lines, name, cfg, indent)

    # Final markers
    for name, cfg in states.items():
        if cfg.get("type") == "final":
            lines.append(f'{ind}{name} --> [*]')

    lines.append('')

    # State blocks (only for states needing them)
    for name, cfg in states.items():
        if _needs_block(cfg):
            _emit_state_block(lines, name, cfg, indent)


def _emit_transitions(lines: list[str], source: str, cfg: dict, indent: int):
    """Emit all transitions from a state as --> lines."""
    ind = '    ' * indent

    # on: event transitions
    on = cfg.get("on", {})
    for event, trans in on.items():
        if event == "*":
            continue
        for t in _ensure_list(trans):
            target = _get_target(t, source)
            label = _format_event_label(event, t)
            lines.append(f'{ind}{source} --> {target} : {label}')

    # always
    for t in _ensure_list(cfg.get("always", [])):
        target = _get_target(t, source)
        label = _format_event_label("always", t)
        lines.append(f'{ind}{source} --> {target} : {label}')

    # after
    after = cfg.get("after", {})
    if isinstance(after, dict):
        for delay, trans in after.items():
            for t in _ensure_list(trans):
                target = _get_target(t, source)
                label = _format_after_label(delay, t)
                lines.append(f'{ind}{source} --> {target} : {label}')

    # invoke done/error
    for inv in _ensure_list(cfg.get("invoke", [])):
        if not inv:
            continue
        for t in _ensure_list(inv.get("onDone", [])):
            target = _get_target(t, source)
            label = _format_event_label("done", t)
            lines.append(f'{ind}{source} --> {target} : {label}')
        for t in _ensure_list(inv.get("onError", [])):
            target = _get_target(t, source)
            label = _format_event_label("error", t)
            lines.append(f'{ind}{source} --> {target} : {label}')

    # onDone (done.state for compound/parallel states)
    for t in _ensure_list(cfg.get("onDone", [])):
        target = _get_target(t, source)
        label = _format_event_label("done.state", t)
        lines.append(f'{ind}{source} --> {target} : {label}')


def _emit_state_block(lines: list[str], name: str, cfg: dict, indent: int):
    """Emit a state { } block with metadata and children."""
    ind = '    ' * indent
    cind = '    ' * (indent + 1)
    stype = cfg.get("type")

    lines.append(f'{ind}state {name} {{')

    # Metadata as %% comments
    if stype == "final":
        lines.append(f'{cind}%% type: final')
    elif stype == "history":
        h = cfg.get("history", "shallow")
        lines.append(f'{cind}%% type: history.deep' if h == "deep" else f'{cind}%% type: history')

    if cfg.get("entry"):
        lines.append(f'{cind}%% entry: {_format_actions(cfg["entry"])}')
    if cfg.get("exit"):
        lines.append(f'{cind}%% exit: {_format_actions(cfg["exit"])}')
    if cfg.get("tags"):
        lines.append(f'{cind}%% tags: {", ".join(cfg["tags"])}')
    if cfg.get("description"):
        lines.append(f'{cind}%% description: "{cfg["description"]}"')
    if cfg.get("id"):
        lines.append(f'{cind}%% id: {cfg["id"]}')

    # Invoke
    for inv in _ensure_list(cfg.get("invoke", [])):
        if not inv:
            continue
        src = inv.get("src", "unknown")
        mods = []
        if inv.get("id"):
            mods.append(f'id: {inv["id"]}')
        if inv.get("input"):
            mods.append(f'input: {_format_value(inv["input"])}')
        if inv.get("systemId"):
            mods.append(f'systemId: {inv["systemId"]}')
        mod_str = f' [{", ".join(mods)}]' if mods else ''
        lines.append(f'{cind}%% invoke: {src}{mod_str}')

    # History target
    if cfg.get("target") and stype == "history":
        lines.append(f'{cind}%% target: {cfg["target"]}')

    # Output on final
    if cfg.get("output") and stype == "final":
        lines.append(f'{cind}%% output: {_format_value(cfg["output"])}')

    # Children
    child_states = cfg.get("states", {})
    if child_states:
        if stype == "parallel":
            items = list(child_states.items())
            for i, (cname, ccfg) in enumerate(items):
                if i > 0:
                    lines.append(f'{cind}--')
                _emit_region(lines, cname, ccfg, indent + 1)
        else:
            _emit_scope(lines, child_states, cfg.get("initial"), indent + 1)

    lines.append(f'{ind}}}')
    lines.append('')


def _emit_region(lines: list[str], name: str, cfg: dict, indent: int):
    """Emit a parallel region as state { full contents }."""
    ind = '    ' * indent
    cind = '    ' * (indent + 1)

    lines.append(f'{ind}state {name} {{')

    # Region metadata
    if cfg.get("entry"):
        lines.append(f'{cind}%% entry: {_format_actions(cfg["entry"])}')
    if cfg.get("exit"):
        lines.append(f'{cind}%% exit: {_format_actions(cfg["exit"])}')

    # Region children
    child_states = cfg.get("states", {})
    if child_states:
        _emit_scope(lines, child_states, cfg.get("initial"), indent + 1)

    lines.append(f'{ind}}}')


# ─── formatting helpers ──────────────────────────────────────────

def _emit_comment_value(lines: list[str], ind: str, key: str, val):
    """Emit a %% key: value, with %% on each continuation line."""
    formatted = _format_value(val)
    parts = formatted.split('\n')
    lines.append(f'{ind}%% {key}: {parts[0]}')
    for part in parts[1:]:
        lines.append(f'{ind}%%   {part}')


def _needs_block(cfg: dict) -> bool:
    return bool(
        cfg.get("states") or cfg.get("entry") or cfg.get("exit") or
        cfg.get("invoke") or cfg.get("tags") or cfg.get("description") or
        cfg.get("type") in ("parallel", "final", "history") or
        cfg.get("id") or cfg.get("target") or cfg.get("output")
    )


def _get_target(t, source: str) -> str:
    if isinstance(t, str):
        return t
    if isinstance(t, dict):
        return t.get("target", source)
    return source


def _format_event_label(event: str, t) -> str:
    if isinstance(t, str):
        return event
    if isinstance(t, dict):
        parts = [event]
        guard = t.get("guard")
        if guard:
            parts.append(f'[{_format_guard(guard)}]')
        actions = t.get("actions")
        if actions:
            parts.append(f'/ {_format_actions(actions)}')
        if t.get("reenter"):
            parts.append('@reenter')
        return ' '.join(parts)
    return event


def _format_after_label(delay, t) -> str:
    if isinstance(t, str):
        return f'after {delay}'
    parts = [f'after {delay}']
    if isinstance(t, dict):
        guard = t.get("guard")
        if guard:
            parts.append(f'[{_format_guard(guard)}]')
        actions = t.get("actions")
        if actions:
            parts.append(f'/ {_format_actions(actions)}')
        if t.get("reenter"):
            parts.append('@reenter')
    return ' '.join(parts)


def _format_wildcard(t) -> str:
    if isinstance(t, str):
        return f'-> {t}'
    parts = []
    if isinstance(t, dict):
        guard = t.get("guard")
        if guard:
            parts.append(f'[{_format_guard(guard)}]')
        actions = t.get("actions")
        if actions:
            parts.append(f'/ {_format_actions(actions)}')
        target = t.get("target")
        if target:
            arrow = '->@' if t.get("reenter") else '->'
            parts.append(f'{arrow} {target}')
    return ' '.join(parts)


def _format_guard(guard) -> str:
    if isinstance(guard, str):
        return guard
    if isinstance(guard, dict):
        gtype = guard.get("type")
        if gtype == "not":
            inner = guard.get("guard", "")
            return f"!{_format_guard(inner)}"
        if gtype == "and":
            return ", ".join(_format_guard(g) for g in guard.get("guards", []))
        if gtype == "or":
            return " | ".join(_format_guard(g) for g in guard.get("guards", []))
        if "params" in guard:
            params = ", ".join(f"{k}: {_format_val_inline(v)}"
                               for k, v in guard["params"].items())
            return f"{gtype}({params})"
        return gtype or str(guard)
    return str(guard)


def _format_actions(actions) -> str:
    if isinstance(actions, str):
        return actions
    if isinstance(actions, list):
        parts = []
        for a in actions:
            if isinstance(a, str):
                parts.append(a)
            elif isinstance(a, dict):
                if a.get("__raw__"):
                    parts.append(a["__raw__"])
                elif "type" in a and "params" in a:
                    params = ", ".join(f"{k}: {_format_val_inline(v)}"
                                       for k, v in a["params"].items())
                    parts.append(f'{a["type"]}({params})')
                elif "type" in a:
                    parts.append(a["type"])
                else:
                    parts.append(str(a))
            else:
                parts.append(str(a))
        return ", ".join(parts)
    if isinstance(actions, dict):
        if actions.get("__raw__"):
            return actions["__raw__"]
        return str(actions)
    return str(actions)


def _format_value(val) -> str:
    if isinstance(val, dict) and val.get("__raw__"):
        return val["__raw__"]
    if isinstance(val, str):
        return val
    return json.dumps(val, indent=2)


def _format_val_inline(val) -> str:
    if isinstance(val, str):
        return f'"{val}"'
    return str(val)


def _ensure_list(val) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]
