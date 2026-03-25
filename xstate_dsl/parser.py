"""Parser: DSL text → Machine AST."""
from __future__ import annotations
import re
from .models import (
    Machine, StateNode, Transition, Invocation,
    Action, Guard, GuardExpr,
)


def parse(text: str) -> Machine:
    """Parse DSL text into a Machine AST."""
    lines = text.split("\n")
    p = _Parser(lines)
    return p.parse()


# ─── helpers ──────────────────────────────────────────────────────

_RE_MACHINE = re.compile(r"^machine:\s*(.+)$")
_RE_VERSION = re.compile(r"^version:\s*(.+)$")
_RE_STATE = re.compile(r"^(\s*)(state|region)\s+(\w+)(.*)?$")
_RE_TRANSITION = re.compile(
    r"^(\s*)"                    # indent
    r"(\*|[A-Z_][A-Z0-9_.]*)"   # event (or *)
    r"(?:\s*\[([^\]]*)\])?"     # [guards]
    r"(?:\s*/\s*(.+?))?"        # / actions
    r"(?:\s*->([@]?)\s*(.+))?"  # -> target
    r"\s*$"
)
_RE_ALWAYS = re.compile(
    r"^(\s*)always"
    r"(?:\s*\[([^\]]*)\])?"
    r"(?:\s*/\s*(.+?))?"
    r"(?:\s*->([@]?)\s*(.+))?"
    r"\s*$"
)
_RE_AFTER = re.compile(
    r"^(\s*)after:\s*(\w+|\d+)"
    r"(?:\s*\[([^\]]*)\])?"
    r"(?:\s*/\s*(.+?))?"
    r"(?:\s*->([@]?)\s*(.+))?"
    r"\s*$"
)
_RE_INVOKE = re.compile(r"^(\s*)invoke:\s*(\w+)(.*)?$")
_RE_DONE = re.compile(
    r"^(\s*)done(?:\.state)?"
    r"(?:\s*\[([^\]]*)\])?"
    r"(?:\s*/\s*(.+?))?"
    r"(?:\s*->([@]?)\s*(.+))?"
    r"\s*$"
)
_RE_DONE_STATE = re.compile(r"^(\s*)done\.state")
_RE_ERROR = re.compile(
    r"^(\s*)error"
    r"(?:\s*\[([^\]]*)\])?"
    r"(?:\s*/\s*(.+?))?"
    r"(?:\s*->([@]?)\s*(.+))?"
    r"\s*$"
)
_RE_ENTRY = re.compile(r"^(\s*)entry:\s*(.+)$")
_RE_EXIT = re.compile(r"^(\s*)exit:\s*(.+)$")
_RE_TARGET = re.compile(r"^(\s*)target:\s*(\w+)\s*$")
_RE_OUTPUT = re.compile(r"^(\s*)output:\s*(.+)$")
_RE_WILDCARD = re.compile(
    r"^(\s*)\*"
    r"(?:\s*\[([^\]]*)\])?"
    r"(?:\s*/\s*(.+?))?"
    r"(?:\s*->([@]?)\s*(.+))?"
    r"\s*$"
)
_RE_GUARDED_BRANCH = re.compile(
    r"^(\s+)"
    r"\[([^\]]*)\]"
    r"(?:\s*/\s*(.+?))?"
    r"(?:\s*->([@]?)\s*(.+))?"
    r"\s*$"
)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _parse_actions(text: str) -> list[Action]:
    """Parse comma-separated action list."""
    if not text:
        return []
    actions = []
    for part in _split_top_level(text):
        part = part.strip()
        if not part:
            continue
        # Check for built-in action patterns
        for kind in ("assign", "raise", "sendTo", "sendParent", "emit", "log", "spawn", "stop", "forwardTo"):
            if part.startswith(kind + "("):
                args = part[len(kind)+1:].rstrip(")")
                actions.append(Action(name=kind, kind=kind, args=args))
                break
        else:
            # Check for parameterized action: name(key: val, ...)
            m = re.match(r"(\w+)\((.+)\)$", part)
            if m:
                params = _parse_params(m.group(2))
                actions.append(Action(name=m.group(1), params=params))
            else:
                actions.append(Action(name=part))
    return actions


def _split_top_level(text: str) -> list[str]:
    """Split by commas respecting parentheses and braces."""
    parts, depth, current = [], 0, []
    for ch in text:
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts


def _parse_guards(text: str) -> GuardExpr | None:
    """Parse guard expression: [a, b] → and, [a | b] → or, [!a] → not."""
    if not text or text.strip() == "else":
        return None
    text = text.strip()
    if "|" in text:
        # OR groups, each element might be AND
        or_parts = [p.strip() for p in text.split("|")]
        children = []
        for p in or_parts:
            if "," in p:
                and_children = [_single_guard(g.strip()) for g in p.split(",")]
                children.append(GuardExpr(op="and", children=and_children))
            else:
                children.append(_single_guard(p))
        return GuardExpr(op="or", children=children)
    if "," in text:
        parts = [p.strip() for p in text.split(",")]
        children = [_single_guard(p) for p in parts]
        return GuardExpr(op="and", children=children)
    return _single_guard(text.strip())


def _single_guard(text: str) -> GuardExpr:
    negated = text.startswith("!")
    name = text.lstrip("!")
    params = None
    m = re.match(r"(\w+)\((.+)\)$", name)
    if m:
        name = m.group(1)
        params = _parse_params(m.group(2))
    return GuardExpr(op="ref", guard=Guard(name=name, negated=negated, params=params))


def _parse_params(text: str) -> dict:
    """Parse key: value pairs."""
    params = {}
    for part in _split_top_level(text):
        part = part.strip()
        if ":" in part:
            k, v = part.split(":", 1)
            params[k.strip()] = v.strip().strip('"').strip("'")
    return params


def _parse_invoke_modifiers(text: str) -> dict:
    """Parse [id: x, input: {...}, systemId: y]."""
    mods = {}
    m = re.search(r"\[(.+?)\]", text)
    if m:
        for part in _split_top_level(m.group(1)):
            part = part.strip()
            if ":" in part:
                k, v = part.split(":", 1)
                mods[k.strip()] = v.strip()
    # Also check for src: outside brackets
    m2 = re.search(r"src:\s*(\w+)", text)
    if m2:
        mods["src"] = m2.group(1)
    return mods


def _parse_state_modifiers(text: str) -> dict:
    """Parse [modifier: value] blocks on state line."""
    mods: dict = {}
    # Find all [...] blocks
    for m in re.finditer(r"\[([^\]]+)\]", text):
        content = m.group(1).strip()
        if content == "initial":
            mods["is_initial"] = True
            continue
        if ":" in content:
            key, val = content.split(":", 1)
            key, val = key.strip(), val.strip()
            if key == "type":
                if val == "history.deep":
                    mods["state_type"] = "history"
                    mods["history_type"] = "deep"
                elif val == "history":
                    mods["state_type"] = "history"
                    mods["history_type"] = "shallow"
                else:
                    mods["state_type"] = val
            elif key == "initial":
                mods["initial"] = val
            elif key == "tags":
                mods["tags"] = [t.strip() for t in val.split(",")]
            elif key == "id":
                mods["state_id"] = val
            elif key == "description":
                mods["description"] = val.strip('"')
            elif key == "meta":
                mods["meta"] = val
    return mods


# ─── main parser ──────────────────────────────────────────────────

class _Parser:
    def __init__(self, lines: list[str]):
        self.lines = lines
        self.pos = 0
        self.machine = Machine(id="unnamed")

    def parse(self) -> Machine:
        while self.pos < len(self.lines):
            line = self.lines[self.pos]
            stripped = line.strip()

            if not stripped or stripped.startswith("#"):
                self.pos += 1
                continue

            m = _RE_MACHINE.match(stripped)
            if m:
                self.machine.id = m.group(1).strip()
                self.pos += 1
                continue

            m = _RE_VERSION.match(stripped)
            if m:
                self.machine.version = m.group(1).strip()
                self.pos += 1
                continue

            if stripped.startswith("context:"):
                self.machine.context = self._collect_block("context:")
                continue
            if stripped.startswith("input:"):
                self.machine.input = self._collect_block("input:")
                continue
            if stripped.startswith("output:") and _indent(line) == 0:
                self.machine.output = self._collect_block("output:")
                continue
            if stripped.startswith("types:"):
                self.machine.types = self._collect_block("types:")
                continue

            m = _RE_STATE.match(line)
            if m:
                state = self._parse_state(line)
                self.machine.root_states[state.name] = state
                if state.is_initial or not self.machine.initial:
                    self.machine.initial = state.name
                continue

            m = _RE_WILDCARD.match(line)
            if m:
                t = self._parse_event_transition(m, wildcard=True)
                self.machine.wildcard_transitions.append(t)
                self.pos += 1
                continue

            self.pos += 1

        return self.machine

    def _collect_block(self, prefix: str) -> str:
        """Collect a possibly multi-line block (e.g., context: { ... })."""
        line = self.lines[self.pos].strip()
        value = line[len(prefix):].strip()
        self.pos += 1

        if "{" in value and "}" not in value:
            # Multi-line brace block
            while self.pos < len(self.lines):
                next_line = self.lines[self.pos]
                value += "\n" + next_line
                self.pos += 1
                if "}" in next_line:
                    break
        elif "(" in value and ")" not in value:
            while self.pos < len(self.lines):
                next_line = self.lines[self.pos]
                value += "\n" + next_line
                self.pos += 1
                if ")" in next_line:
                    break
        return value

    def _parse_state(self, first_line: str) -> StateNode:
        m = _RE_STATE.match(first_line)
        kind = m.group(2)  # 'state' or 'region'
        name = m.group(3)
        rest = m.group(4) or ""
        base_indent = _indent(first_line)

        mods = _parse_state_modifiers(rest)
        node = StateNode(name=name, **{k: v for k, v in mods.items()})

        self.pos += 1
        current_invoke: Invocation | None = None
        last_event_for_branches: str | None = None

        while self.pos < len(self.lines):
            line = self.lines[self.pos]
            stripped = line.strip()
            ind = _indent(line)

            if not stripped or stripped.startswith("#"):
                self.pos += 1
                continue

            # Must be indented deeper than state
            if ind <= base_indent and stripped:
                break

            # entry / exit
            me = _RE_ENTRY.match(line)
            if me:
                node.entry.extend(_parse_actions(me.group(2)))
                self.pos += 1
                continue

            mx = _RE_EXIT.match(line)
            if mx:
                node.exit.extend(_parse_actions(mx.group(2)))
                self.pos += 1
                continue

            # target (for history states)
            mt = _RE_TARGET.match(line)
            if mt:
                node.history_target = mt.group(2)
                self.pos += 1
                continue

            # output (on final states)
            mo = _RE_OUTPUT.match(line)
            if mo:
                node.output = mo.group(2).strip()
                self.pos += 1
                continue

            # invoke
            mi = _RE_INVOKE.match(line)
            if mi:
                invoke_indent = _indent(line)
                src = mi.group(2)
                invoke_rest = mi.group(3) or ""
                mods = _parse_invoke_modifiers(invoke_rest)
                inv = Invocation(
                    src=mods.get("src", src),
                    id=mods.get("id"),
                    input=mods.get("input"),
                    system_id=mods.get("systemId"),
                )
                node.invocations.append(inv)
                current_invoke = inv
                self.pos += 1
                continue

            # done / done.state / error under invoke
            md = _RE_DONE.match(line)
            is_done_state = bool(_RE_DONE_STATE.match(line))
            if md:
                t = Transition(
                    guards=_parse_guards(md.group(2)),
                    actions=_parse_actions(md.group(3)),
                    reenter=md.group(4) == "@",
                    target=md.group(5).strip() if md.group(5) else None,
                )
                if is_done_state:
                    node.on_done.append(t)
                elif current_invoke:
                    current_invoke.on_done.append(t)
                else:
                    node.on_done.append(t)
                self.pos += 1
                continue

            mer = _RE_ERROR.match(line)
            if mer:
                t = Transition(
                    guards=_parse_guards(mer.group(2)),
                    actions=_parse_actions(mer.group(3)),
                    reenter=mer.group(4) == "@",
                    target=mer.group(5).strip() if mer.group(5) else None,
                )
                if current_invoke:
                    current_invoke.on_error.append(t)
                self.pos += 1
                continue

            # always
            ma = _RE_ALWAYS.match(line)
            if ma:
                current_invoke = None
                t = Transition(
                    guards=_parse_guards(ma.group(2)),
                    actions=_parse_actions(ma.group(3)),
                    reenter=ma.group(4) == "@",
                    target=ma.group(5).strip() if ma.group(5) else None,
                )
                node.always.append(t)
                self.pos += 1
                continue

            # after
            maf = _RE_AFTER.match(line)
            if maf:
                current_invoke = None
                delay = maf.group(2)
                try:
                    delay = int(delay)
                except ValueError:
                    pass
                t = Transition(
                    delay=delay,
                    guards=_parse_guards(maf.group(3)),
                    actions=_parse_actions(maf.group(4)),
                    reenter=maf.group(5) == "@",
                    target=maf.group(6).strip() if maf.group(6) else None,
                )
                node.after.append(t)
                self.pos += 1
                continue

            # child state / region
            ms = _RE_STATE.match(line)
            if ms:
                current_invoke = None
                child = self._parse_state(line)
                node.children[child.name] = child
                if child.is_initial or (node.initial is None and not node.state_type == "parallel"):
                    if node.initial is None:
                        node.initial = child.name
                continue

            # guarded branch (continuation of previous event)
            mb = _RE_GUARDED_BRANCH.match(line)
            if mb and last_event_for_branches:
                t = Transition(
                    event=last_event_for_branches,
                    guards=_parse_guards(mb.group(2)),
                    actions=_parse_actions(mb.group(3)),
                    reenter=mb.group(4) == "@",
                    target=mb.group(5).strip() if mb.group(5) else None,
                )
                node.transitions.append(t)
                self.pos += 1
                continue

            # wildcard
            mw = _RE_WILDCARD.match(line)
            if mw:
                current_invoke = None
                t = self._parse_event_transition_from_groups(
                    "*", mw.group(2), mw.group(3), mw.group(4), mw.group(5)
                )
                node.transitions.append(t)
                last_event_for_branches = "*"
                self.pos += 1
                continue

            # normal event transition
            mt = _RE_TRANSITION.match(line)
            if mt:
                current_invoke = None
                event = mt.group(2)
                # Check if next lines are guarded branches (event alone on line)
                if not mt.group(3) and not mt.group(4) and not mt.group(6):
                    # Bare event — check for branches below
                    last_event_for_branches = event
                    self.pos += 1
                    continue
                t = self._parse_event_transition_from_groups(
                    event, mt.group(3), mt.group(4), mt.group(5), mt.group(6)
                )
                node.transitions.append(t)
                last_event_for_branches = event
                self.pos += 1
                continue

            self.pos += 1

        return node

    def _parse_event_transition(self, m, wildcard=False) -> Transition:
        return self._parse_event_transition_from_groups(
            "*" if wildcard else m.group(2),
            m.group(2) if wildcard else m.group(3),
            m.group(3) if wildcard else m.group(4),
            m.group(4) if wildcard else m.group(5),
            m.group(5) if wildcard else m.group(6),
        )

    def _parse_event_transition_from_groups(
        self, event, guards_str, actions_str, reenter_str, target_str
    ) -> Transition:
        return Transition(
            event=event,
            guards=_parse_guards(guards_str),
            actions=_parse_actions(actions_str),
            reenter=reenter_str == "@",
            target=target_str.strip() if target_str else None,
        )
