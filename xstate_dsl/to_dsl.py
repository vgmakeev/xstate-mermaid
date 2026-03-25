"""Convert XState v5 JSON config dict → DSL text."""
from __future__ import annotations
import json
from typing import Any


def to_dsl(xstate_config: dict[str, Any]) -> str:
    """Convert XState v5 config dict (or {setup, config} pair) to DSL text."""
    if "config" in xstate_config and "setup" in xstate_config:
        config = xstate_config["config"]
    else:
        config = xstate_config

    lines: list[str] = []

    # Machine header
    lines.append(f"machine: {config.get('id', 'unnamed')}")
    if config.get("version"):
        lines.append(f"version: {config['version']}")

    ctx = config.get("context")
    if ctx:
        lines.append(f"context: {_format_value(ctx)}")

    inp = config.get("input")
    if inp:
        lines.append(f"input: {_format_value(inp)}")

    out = config.get("output")
    if out and not config.get("states"):
        lines.append(f"output: {_format_value(out)}")

    lines.append("")

    # States
    states = config.get("states", {})
    initial = config.get("initial")

    for name, state_cfg in states.items():
        _emit_state(lines, name, state_cfg, indent=0,
                    is_initial=(name == initial and len(states) > 1))

    # Root-level wildcard
    on = config.get("on", {})
    if "*" in on:
        for t in _ensure_list(on["*"]):
            lines.append(_format_transition("*", t))

    return "\n".join(lines).rstrip() + "\n"


def _emit_state(lines: list[str], name: str, cfg: dict, indent: int,
                is_initial: bool = False, is_region: bool = False):
    pad = "  " * indent
    keyword = "region" if is_region else "state"

    # Build modifier string
    mods = []
    stype = cfg.get("type")
    if stype == "history":
        h = cfg.get("history", "shallow")
        mods.append(f"type: history.deep" if h == "deep" else "type: history")
    elif stype:
        mods.append(f"type: {stype}")

    if is_initial:
        mods.append("initial")
    if cfg.get("initial"):
        mods.append(f"initial: {cfg['initial']}")
    if cfg.get("id"):
        mods.append(f"id: {cfg['id']}")
    if cfg.get("tags"):
        mods.append(f"tags: {', '.join(cfg['tags'])}")
    if cfg.get("description"):
        mods.append(f'description: "{cfg["description"]}"')

    mod_str = " ".join(f"[{m}]" for m in mods)
    header = f"{pad}{keyword} {name}"
    if mod_str:
        header += f" {mod_str}"
    lines.append(header)

    child_pad = "  " * (indent + 1)

    # entry / exit
    if cfg.get("entry"):
        actions = _format_actions(cfg["entry"])
        lines.append(f"{child_pad}entry: {actions}")
    if cfg.get("exit"):
        actions = _format_actions(cfg["exit"])
        lines.append(f"{child_pad}exit: {actions}")

    # invoke
    invocations = _ensure_list(cfg.get("invoke", []))
    for inv in invocations:
        if not inv:
            continue
        src = inv.get("src", "unknown")
        inv_mods = []
        if inv.get("id"):
            inv_mods.append(f"id: {inv['id']}")
        if inv.get("input"):
            inv_mods.append(f"input: {_format_value(inv['input'])}")
        if inv.get("systemId"):
            inv_mods.append(f"systemId: {inv['systemId']}")
        mod_str = f" [{', '.join(inv_mods)}]" if inv_mods else ""
        lines.append(f"{child_pad}invoke: {src}{mod_str}")

        inv_pad = "  " * (indent + 2)
        for t in _ensure_list(inv.get("onDone", [])):
            lines.append(f"{inv_pad}{_format_transition('done', t)}")
        for t in _ensure_list(inv.get("onError", [])):
            lines.append(f"{inv_pad}{_format_transition('error', t)}")

    # always
    for t in _ensure_list(cfg.get("always", [])):
        lines.append(f"{child_pad}{_format_transition('always', t)}")

    # after
    after = cfg.get("after", {})
    if isinstance(after, dict):
        for delay, trans in after.items():
            for t in _ensure_list(trans):
                lines.append(f"{child_pad}{_format_after(delay, t)}")

    # on (event transitions)
    on = cfg.get("on", {})
    for event, trans in on.items():
        if event == "*":
            # Wildcard at state level
            for t in _ensure_list(trans):
                lines.append(f"{child_pad}{_format_transition('*', t)}")
        else:
            trans_list = _ensure_list(trans)
            if len(trans_list) == 1:
                lines.append(f"{child_pad}{_format_transition(event, trans_list[0])}")
            else:
                # Multi-branch — event on one line, branches indented
                lines.append(f"{child_pad}{event}")
                branch_pad = "  " * (indent + 2)
                for t in trans_list:
                    lines.append(f"{branch_pad}{_format_branch(t)}")

    # onDone (done.state for compound states)
    for t in _ensure_list(cfg.get("onDone", [])):
        lines.append(f"{child_pad}{_format_transition('done.state', t)}")

    # History target
    if cfg.get("target") and stype == "history":
        lines.append(f"{child_pad}target: {cfg['target']}")

    # Output on final states
    if cfg.get("output") and stype == "final":
        lines.append(f"{child_pad}output: {_format_value(cfg['output'])}")

    # Child states
    child_states = cfg.get("states", {})
    child_initial = cfg.get("initial")
    is_parallel = (stype == "parallel")

    if child_states:
        lines.append("")
        for cname, ccfg in child_states.items():
            _emit_state(
                lines, cname, ccfg, indent + 1,
                is_initial=(cname == child_initial and not is_parallel),
                is_region=is_parallel,
            )

    lines.append("")


def _format_transition(keyword: str, t) -> str:
    """Format a single transition line."""
    if isinstance(t, str):
        # Simple target string
        return f"{keyword} -> {t}"

    if isinstance(t, dict):
        parts = [keyword]

        guard = t.get("guard")
        if guard:
            parts.append(f"[{_format_guard(guard)}]")

        actions = t.get("actions")
        if actions:
            parts.append(f"/ {_format_actions(actions)}")

        target = t.get("target")
        reenter = t.get("reenter", False)
        if target:
            arrow = "->@" if reenter else "->"
            parts.append(f"{arrow} {target}")

        return " ".join(parts)

    return keyword


def _format_branch(t) -> str:
    """Format a guarded branch (no event name)."""
    if isinstance(t, str):
        return f"-> {t}"

    parts = []
    guard = t.get("guard")
    if guard:
        parts.append(f"[{_format_guard(guard)}]")
    else:
        parts.append("[else]")

    actions = t.get("actions")
    if actions:
        parts.append(f"/ {_format_actions(actions)}")

    target = t.get("target")
    reenter = t.get("reenter", False)
    if target:
        arrow = "->@" if reenter else "->"
        parts.append(f"{arrow} {target}")

    return " ".join(parts)


def _format_after(delay, t) -> str:
    """Format an after transition."""
    if isinstance(t, str):
        return f"after: {delay} -> {t}"

    parts = [f"after: {delay}"]

    guard = t.get("guard") if isinstance(t, dict) else None
    if guard:
        parts.append(f"[{_format_guard(guard)}]")

    actions = t.get("actions") if isinstance(t, dict) else None
    if actions:
        parts.append(f"/ {_format_actions(actions)}")

    target = t.get("target") if isinstance(t, dict) else None
    reenter = t.get("reenter", False) if isinstance(t, dict) else False
    if target:
        arrow = "->@" if reenter else "->"
        parts.append(f"{arrow} {target}")

    return " ".join(parts)


def _format_guard(guard) -> str:
    """Format a guard expression."""
    if isinstance(guard, str):
        return guard
    if isinstance(guard, dict):
        gtype = guard.get("type")
        if gtype == "not":
            inner = guard.get("guard", "")
            return f"!{_format_guard(inner)}"
        if gtype == "and":
            guards = guard.get("guards", [])
            return ", ".join(_format_guard(g) for g in guards)
        if gtype == "or":
            guards = guard.get("guards", [])
            return " | ".join(_format_guard(g) for g in guards)
        # Named guard with params
        if "params" in guard:
            params = ", ".join(f"{k}: {_format_val_inline(v)}"
                               for k, v in guard["params"].items())
            return f"{gtype}({params})"
        return gtype or str(guard)
    return str(guard)


def _format_actions(actions) -> str:
    """Format actions list to DSL string."""
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
                    parts.append(f"{a['type']}({params})")
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
    """Format a value for DSL output."""
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
