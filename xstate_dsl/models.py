"""Data models representing the DSL AST and XState config."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Guard:
    name: str
    negated: bool = False
    params: dict[str, Any] | None = None


@dataclass
class GuardExpr:
    """Composite guard expression."""
    op: str  # 'and' | 'or' | 'not' | 'ref'
    children: list[GuardExpr | Guard] = field(default_factory=list)
    guard: Guard | None = None  # for 'ref' and 'not'

    def to_xstate(self) -> dict | str:
        if self.op == "ref":
            g = self.guard
            base = g.name if not g.params else {"type": g.name, "params": g.params}
            return {"type": "not", "guard": base} if g.negated else base
        if self.op == "not":
            inner = self.children[0].to_xstate() if self.children else self.guard.name
            return {"type": "not", "guard": inner}
        items = [c.to_xstate() for c in self.children]
        if len(items) == 1:
            return items[0]
        return {"type": self.op, "guards": items}


@dataclass
class Action:
    name: str
    kind: str = "ref"  # ref | assign | raise | sendTo | emit | log | spawn | stop | forwardTo | sendParent
    args: Any = None
    params: dict[str, Any] | None = None


@dataclass
class Transition:
    event: str | None = None  # None for always
    target: str | None = None
    guards: GuardExpr | None = None
    actions: list[Action] = field(default_factory=list)
    reenter: bool = False
    delay: str | int | None = None  # for after transitions
    description: str | None = None


@dataclass
class Invocation:
    src: str
    id: str | None = None
    input: str | None = None
    system_id: str | None = None
    on_done: list[Transition] = field(default_factory=list)
    on_error: list[Transition] = field(default_factory=list)


@dataclass
class StateNode:
    name: str
    state_type: str | None = None  # parallel | final | history
    history_type: str | None = None  # shallow | deep
    initial: str | None = None
    is_initial: bool = False
    tags: list[str] = field(default_factory=list)
    meta: dict[str, Any] | None = None
    description: str | None = None
    state_id: str | None = None
    entry: list[Action] = field(default_factory=list)
    exit: list[Action] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)
    always: list[Transition] = field(default_factory=list)
    after: list[Transition] = field(default_factory=list)
    invocations: list[Invocation] = field(default_factory=list)
    children: dict[str, StateNode] = field(default_factory=dict)
    history_target: str | None = None  # default for history states
    output: str | None = None
    on_done: list[Transition] = field(default_factory=list)  # done.state


@dataclass
class Machine:
    id: str
    version: str | None = None
    context: str | None = None
    input: str | None = None
    output: str | None = None
    types: str | None = None
    root_states: dict[str, StateNode] = field(default_factory=dict)
    initial: str | None = None
    wildcard_transitions: list[Transition] = field(default_factory=list)
