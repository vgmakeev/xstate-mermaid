"""Parser: Mermaid stateDiagram-v2 text → Machine AST."""
from __future__ import annotations
import re
from .models import (
    Machine, StateNode, Transition, Invocation,
    Action, Guard, GuardExpr,
)


def parse(text: str) -> Machine:
    """Parse Mermaid stateDiagram-v2 text into a Machine AST."""
    return _MermaidParser(text).parse()


# ─── helpers ──────────────────────────────────────────────────────

def _parse_actions(text: str) -> list[Action]:
    """Parse comma-separated action list."""
    if not text:
        return []
    actions = []
    for part in _split_top_level(text):
        part = part.strip()
        if not part:
            continue
        for kind in ("assign", "raise", "sendTo", "sendParent", "emit", "log", "spawn", "stop", "forwardTo"):
            if part.startswith(kind + "("):
                args = part[len(kind)+1:].rstrip(")")
                actions.append(Action(name=kind, kind=kind, args=args))
                break
        else:
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
    m2 = re.search(r"src:\s*(\w+)", text)
    if m2:
        mods["src"] = m2.group(1)
    return mods


# ─── Mermaid parser ──────────────────────────────────────────────

_RE_STATE_BLOCK = re.compile(r'\s*state\s+(\w+)\s*\{\s*$')
_RE_STATE_DESC = re.compile(r'\s*state\s+"([^"]+)"\s+as\s+(\w+)\s*$')
_RE_TRANSITION = re.compile(r'\s*(\[\*\]|\w+)\s*-->\s*(\[\*\]|\w+)(?:\s*:\s*(.+))?\s*$')


class _MermaidParser:
    def __init__(self, text: str):
        self.lines = text.split('\n')
        self.pos = 0
        self.machine = Machine(id='unnamed')

    def parse(self) -> Machine:
        self._skip_header()
        self._parse_scope(None, self.machine.root_states, [])
        if not self.machine.initial and self.machine.root_states:
            self.machine.initial = next(iter(self.machine.root_states))
        return self.machine

    def _skip_header(self):
        while self.pos < len(self.lines):
            stripped = self.lines[self.pos].strip()
            if stripped.startswith('stateDiagram'):
                self.pos += 1
                return
            if stripped and (stripped.startswith('%%') or stripped.startswith('[*]')
                           or stripped.startswith('state') or _RE_TRANSITION.match(stripped)):
                return
            if not stripped:
                self.pos += 1
                continue
            self.pos += 1

    def _parse_scope(self, parent: StateNode | None, states: dict[str, StateNode],
                     ancestor_states: list[dict[str, StateNode]]):
        """Parse a scope (root or inside state {}). Defers transition resolution."""
        pending: list[tuple[str, str, str | None]] = []

        while self.pos < len(self.lines):
            line = self.lines[self.pos]
            stripped = line.strip()

            if not stripped:
                self.pos += 1
                continue
            if stripped == '}':
                self.pos += 1
                break
            if stripped == '--':
                if parent:
                    parent.state_type = 'parallel'
                self.pos += 1
                continue
            if stripped.startswith('%%'):
                self._handle_comment(parent, states)
                continue

            m = _RE_STATE_DESC.match(line)
            if m:
                desc, name = m.group(1), m.group(2)
                node = states.setdefault(name, StateNode(name=name))
                node.description = desc
                self.pos += 1
                continue

            m = _RE_STATE_BLOCK.match(line)
            if m:
                name = m.group(1)
                node = states.setdefault(name, StateNode(name=name))
                self.pos += 1
                self._parse_scope(node, node.children, ancestor_states + [states])
                continue

            m = _RE_TRANSITION.match(line)
            if m:
                pending.append((m.group(1), m.group(2), m.group(3)))
                self.pos += 1
                continue

            self.pos += 1

        # Resolve transitions after all state blocks are parsed
        for source, target, label in pending:
            self._resolve_transition(source, target, label, parent, states, ancestor_states)

    def _handle_comment(self, parent: StateNode | None, states: dict[str, StateNode]):
        stripped = self.lines[self.pos].strip()
        content = stripped[2:].strip()

        if parent is None:
            if content.startswith('machine:'):
                self.machine.id = content[8:].strip()
                self.pos += 1
                return
            if content.startswith('version:'):
                self.machine.version = content[8:].strip()
                self.pos += 1
                return
            for prefix, attr in [('context:', 'context'), ('input:', 'input'),
                                  ('output:', 'output'), ('types:', 'types')]:
                if content.startswith(prefix):
                    setattr(self.machine, attr, self._collect_multiline_value(prefix))
                    return
            m = re.match(r'on\s+\*\s*:\s*(.+)', content)
            if m:
                self._parse_wildcard(m.group(1).strip())
                self.pos += 1
                return
        else:
            if content.startswith('entry:'):
                parent.entry.extend(_parse_actions(content[6:].strip()))
                self.pos += 1
                return
            if content.startswith('exit:'):
                parent.exit.extend(_parse_actions(content[5:].strip()))
                self.pos += 1
                return
            if content.startswith('invoke:'):
                self._parse_invoke(content[7:].strip(), parent)
                self.pos += 1
                return
            if content.startswith('tags:'):
                parent.tags = [t.strip() for t in content[5:].split(',')]
                self.pos += 1
                return
            if content.startswith('type:'):
                tval = content[5:].strip()
                if tval == 'history.deep':
                    parent.state_type = 'history'
                    parent.history_type = 'deep'
                elif tval == 'history':
                    parent.state_type = 'history'
                    parent.history_type = 'shallow'
                else:
                    parent.state_type = tval
                self.pos += 1
                return
            if content.startswith('description:'):
                parent.description = content[12:].strip().strip('"')
                self.pos += 1
                return
            if content.startswith('id:'):
                parent.state_id = content[3:].strip()
                self.pos += 1
                return
            if content.startswith('initial:'):
                parent.initial = content[8:].strip()
                self.pos += 1
                return
            if content.startswith('target:'):
                parent.history_target = content[7:].strip()
                self.pos += 1
                return
            if content.startswith('output:'):
                parent.output = content[7:].strip()
                self.pos += 1
                return

        self.pos += 1

    def _collect_multiline_value(self, prefix: str) -> str:
        stripped = self.lines[self.pos].strip()
        content = stripped[2:].strip()
        value = content[len(prefix):].strip()
        self.pos += 1

        if '{' in value and '}' not in value:
            depth = value.count('{') - value.count('}')
            while depth > 0 and self.pos < len(self.lines):
                ns = self.lines[self.pos].strip()
                if not ns.startswith('%%'):
                    break
                nc = ns[2:].strip()
                value += '\n' + nc
                depth += nc.count('{') - nc.count('}')
                self.pos += 1
        elif '(' in value and ')' not in value:
            depth = value.count('(') - value.count(')')
            while depth > 0 and self.pos < len(self.lines):
                ns = self.lines[self.pos].strip()
                if not ns.startswith('%%'):
                    break
                nc = ns[2:].strip()
                value += '\n' + nc
                depth += nc.count('(') - nc.count(')')
                self.pos += 1

        return value

    def _parse_invoke(self, text: str, parent: StateNode):
        m = re.match(r'(\w+)(.*)', text)
        if not m:
            return
        src = m.group(1)
        rest = m.group(2).strip()
        mods = _parse_invoke_modifiers(rest)
        parent.invocations.append(Invocation(
            src=mods.get('src', src),
            id=mods.get('id'),
            input=mods.get('input'),
            system_id=mods.get('systemId'),
        ))

    def _parse_wildcard(self, text: str):
        target = None
        reenter = False
        m = re.search(r'->([@]?)\s*(\S+)\s*$', text)
        if m:
            reenter = m.group(1) == '@'
            target = m.group(2)
            text = text[:m.start()].strip()
        guards, actions = self._parse_guard_actions(text)
        self.machine.wildcard_transitions.append(Transition(
            event='*', guards=guards, actions=actions,
            target=target, reenter=reenter,
        ))

    def _resolve_transition(self, source: str, target: str, label: str | None,
                            parent: StateNode | None, states: dict[str, StateNode],
                            ancestor_states: list[dict[str, StateNode]]):
        # [*] --> X = initial
        if source == '[*]':
            if parent is None:
                self.machine.initial = target
            else:
                parent.initial = target
            states.setdefault(target, StateNode(name=target))
            return

        # X --> [*] = final
        if target == '[*]':
            node = states.setdefault(source, StateNode(name=source))
            node.state_type = 'final'
            return

        # Ensure source exists in current scope
        src_node = states.setdefault(source, StateNode(name=source))

        # Create target in current scope only if not found in any ancestor
        if target not in states:
            found_in_ancestor = any(target in a for a in ancestor_states)
            if not found_in_ancestor:
                states[target] = StateNode(name=target)

        if not label:
            src_node.transitions.append(Transition(target=target))
            return

        label = label.strip()
        event, guards, actions, reenter, delay = self._parse_label(label)

        # Self-loop without reenter = internal transition (no target in XState)
        actual_target = target
        if source == target and not reenter:
            actual_target = None

        t = Transition(target=actual_target, guards=guards, actions=actions,
                       reenter=reenter, delay=delay)

        if event == 'always':
            src_node.always.append(t)
        elif delay is not None:
            src_node.after.append(t)
        elif event == 'done.state':
            src_node.on_done.append(t)
        elif event == 'done':
            if src_node.invocations:
                src_node.invocations[-1].on_done.append(t)
            else:
                src_node.on_done.append(t)
        elif event == 'error':
            if src_node.invocations:
                src_node.invocations[-1].on_error.append(t)
            else:
                t.event = 'error'
                src_node.transitions.append(t)
        else:
            t.event = event
            src_node.transitions.append(t)

    def _parse_label(self, label: str):
        """Parse label → (event, guards, actions, reenter, delay)."""
        reenter = False
        if label.endswith('@reenter'):
            reenter = True
            label = label[:-8].strip()

        # after DELAY ...
        m = re.match(r'after\s+(\d+|\w+)(.*)', label)
        if m:
            d = m.group(1)
            try:
                d = int(d)
            except ValueError:
                pass
            guards, actions = self._parse_guard_actions(m.group(2).strip())
            return None, guards, actions, reenter, d

        # always
        if label == 'always' or label.startswith('always ') or label.startswith('always['):
            guards, actions = self._parse_guard_actions(label[6:].strip())
            return 'always', guards, actions, reenter, None

        # done.state
        if label == 'done.state' or label.startswith('done.state '):
            guards, actions = self._parse_guard_actions(label[10:].strip())
            return 'done.state', guards, actions, reenter, None

        # done
        if label == 'done' or re.match(r'done[\s\[/]', label):
            guards, actions = self._parse_guard_actions(label[4:].strip())
            return 'done', guards, actions, reenter, None

        # error
        if label == 'error' or re.match(r'error[\s\[/]', label):
            guards, actions = self._parse_guard_actions(label[5:].strip())
            return 'error', guards, actions, reenter, None

        # Regular event
        m = re.match(r'(\*|[A-Za-z_]\w*)(.*)', label)
        if m:
            guards, actions = self._parse_guard_actions(m.group(2).strip())
            return m.group(1), guards, actions, reenter, None

        return label, None, [], reenter, None

    def _parse_guard_actions(self, text: str):
        guards = None
        actions = []
        if not text:
            return guards, actions
        m = re.match(r'\[([^\]]*)\](.*)', text)
        if m:
            guards = _parse_guards(m.group(1))
            text = m.group(2).strip()
        if text.startswith('/'):
            actions = _parse_actions(text[1:].strip())
        return guards, actions
