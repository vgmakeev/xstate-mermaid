"""Convert Machine AST → XState v5 JSON config dict."""
from __future__ import annotations
from typing import Any
from .models import (
    Machine, StateNode, Transition, Invocation,
    Action, GuardExpr,
)


def to_xstate(machine: Machine) -> dict[str, Any]:
    """Convert Machine AST to XState v5 createMachine config dict."""
    config: dict[str, Any] = {"id": machine.id}

    if machine.version:
        config["version"] = machine.version
    if machine.context:
        config["context"] = _raw(machine.context)
    if machine.initial:
        config["initial"] = machine.initial

    # Collect all action/guard/actor names for setup()
    refs = _Refs()
    for s in machine.root_states.values():
        _collect_refs(s, refs)
    for t in machine.wildcard_transitions:
        _collect_transition_refs(t, refs)

    states = {}
    for name, s in machine.root_states.items():
        states[name] = _state_to_config(s)

    config["states"] = states

    # Wildcard → on: { "*": [...] } at root level
    if machine.wildcard_transitions:
        on = config.setdefault("on", {})
        on["*"] = [_transition_to_config(t) for t in machine.wildcard_transitions]

    # Setup block (references)
    setup: dict[str, Any] = {}
    if refs.actions:
        setup["actions"] = {a: f"/* implement {a} */" for a in sorted(refs.actions)}
    if refs.guards:
        setup["guards"] = {g: f"/* implement {g} */" for g in sorted(refs.guards)}
    if refs.actors:
        setup["actors"] = {a: f"/* implement {a} */" for a in sorted(refs.actors)}

    return {"setup": setup, "config": config}


class _Refs:
    def __init__(self):
        self.actions: set[str] = set()
        self.guards: set[str] = set()
        self.actors: set[str] = set()


def _collect_refs(node: StateNode, refs: _Refs):
    for a in node.entry + node.exit:
        if a.kind == "ref":
            refs.actions.add(a.name)
    for t in node.transitions + node.always + node.after + node.on_done:
        _collect_transition_refs(t, refs)
    for inv in node.invocations:
        refs.actors.add(inv.src)
        for t in inv.on_done + inv.on_error:
            _collect_transition_refs(t, refs)
    for child in node.children.values():
        _collect_refs(child, refs)


def _collect_transition_refs(t: Transition, refs: _Refs):
    for a in t.actions:
        if a.kind == "ref":
            refs.actions.add(a.name)
    if t.guards:
        _collect_guard_refs(t.guards, refs)


def _collect_guard_refs(g: GuardExpr, refs: _Refs):
    if g.op == "ref" and g.guard:
        refs.guards.add(g.guard.name)
    for c in g.children:
        _collect_guard_refs(c, refs)


def _state_to_config(node: StateNode) -> dict[str, Any]:
    config: dict[str, Any] = {}

    if node.state_type:
        config["type"] = node.state_type
        if node.state_type == "history" and node.history_type == "deep":
            config["history"] = "deep"
    if node.state_id:
        config["id"] = node.state_id
    if node.initial:
        config["initial"] = node.initial
    if node.tags:
        config["tags"] = node.tags
    if node.description:
        config["description"] = node.description
    if node.meta:
        config["meta"] = _raw(node.meta)

    if node.entry:
        config["entry"] = _actions_to_config(node.entry)
    if node.exit:
        config["exit"] = _actions_to_config(node.exit)

    # Transitions → on: {}
    if node.transitions:
        on: dict[str, Any] = {}
        for t in node.transitions:
            event = t.event or "*"
            tc = _transition_to_config(t)
            if event in on:
                if isinstance(on[event], list):
                    on[event].append(tc)
                else:
                    on[event] = [on[event], tc]
            else:
                on[event] = tc
        config["on"] = on

    # always
    if node.always:
        config["always"] = [_transition_to_config(t) for t in node.always]

    # after
    if node.after:
        after: dict = {}
        for t in node.after:
            key = t.delay if t.delay is not None else 0
            tc = _transition_to_config(t)
            if key in after:
                if isinstance(after[key], list):
                    after[key].append(tc)
                else:
                    after[key] = [after[key], tc]
            else:
                after[key] = tc
        config["after"] = after

    # invoke
    if node.invocations:
        invokes = []
        for inv in node.invocations:
            ic: dict[str, Any] = {"src": inv.src}
            if inv.id:
                ic["id"] = inv.id
            if inv.input:
                ic["input"] = _raw(inv.input)
            if inv.system_id:
                ic["systemId"] = inv.system_id
            if inv.on_done:
                ic["onDone"] = (
                    [_transition_to_config(t) for t in inv.on_done]
                    if len(inv.on_done) > 1
                    else _transition_to_config(inv.on_done[0])
                )
            if inv.on_error:
                ic["onError"] = (
                    [_transition_to_config(t) for t in inv.on_error]
                    if len(inv.on_error) > 1
                    else _transition_to_config(inv.on_error[0])
                )
            invokes.append(ic)
        config["invoke"] = invokes if len(invokes) > 1 else invokes[0]

    # onDone (done.state)
    if node.on_done:
        config["onDone"] = (
            [_transition_to_config(t) for t in node.on_done]
            if len(node.on_done) > 1
            else _transition_to_config(node.on_done[0])
        )

    # Children
    if node.children:
        states = {}
        for name, child in node.children.items():
            states[name] = _state_to_config(child)
        config["states"] = states

    # History target
    if node.history_target:
        config["target"] = node.history_target

    # Output
    if node.output:
        config["output"] = _raw(node.output)

    return config


def _transition_to_config(t: Transition) -> dict[str, Any] | str:
    """Convert a Transition to XState config."""
    # Simple case: just a target
    if t.target and not t.guards and not t.actions and not t.reenter:
        return t.target

    config: dict[str, Any] = {}
    if t.target:
        config["target"] = t.target
    if t.guards:
        config["guard"] = t.guards.to_xstate()
    if t.actions:
        config["actions"] = _actions_to_config(t.actions)
    if t.reenter:
        config["reenter"] = True
    return config


def _actions_to_config(actions: list[Action]) -> Any:
    items = []
    for a in actions:
        if a.kind == "ref":
            if a.params:
                items.append({"type": a.name, "params": a.params})
            else:
                items.append(a.name)
        else:
            # Built-in: assign, raise, sendTo, etc.
            items.append(_raw(f"{a.kind}({a.args})") if a.args else a.kind)
    return items[0] if len(items) == 1 else items


def _raw(value):
    """Return a raw expression marker — for code generation these would need eval."""
    if isinstance(value, str):
        return {"__raw__": value}
    return value
