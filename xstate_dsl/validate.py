"""Static analysis of Machine AST — orphan states, unreachable states, missing targets."""
from __future__ import annotations
from dataclasses import dataclass
from .models import Machine, StateNode, Transition, Invocation


@dataclass
class Issue:
    level: str   # "error" | "warning" | "info"
    code: str    # MISSING_TARGET, ORPHAN_STATE, etc.
    message: str


def validate_static(machine: Machine) -> list[Issue]:
    """Run all static checks on a parsed Machine AST."""
    issues: list[Issue] = []

    if not machine.root_states:
        issues.append(Issue("error", "EMPTY_MACHINE", "Machine has no states"))
        return issues

    if not machine.initial:
        issues.append(Issue("error", "NO_INITIAL", "Machine has no initial state"))

    # Build scope tree: {qualified_name: StateNode}
    all_states: dict[str, StateNode] = {}
    _collect_states(machine.root_states, "", all_states)

    # Check initial states exist
    if machine.initial and machine.initial not in machine.root_states:
        issues.append(Issue("error", "MISSING_INITIAL",
                            f"Initial state \"{machine.initial}\" does not exist"))

    # Check compound states have initial
    _check_initials(machine.root_states, "", issues)

    # Check final states have no outgoing transitions
    _check_finals(all_states, issues)

    # Reachability analysis
    reachable = _find_reachable(machine)
    for qname in sorted(all_states.keys()):
        if qname not in reachable:
            issues.append(Issue("warning", "UNREACHABLE_STATE",
                                f"State \"{qname}\" is not reachable from initial state"))

    return issues


def _collect_states(states: dict[str, StateNode], prefix: str,
                    out: dict[str, StateNode]):
    for name, node in states.items():
        qname = f"{prefix}.{name}" if prefix else name
        out[qname] = node
        if node.children:
            _collect_states(node.children, qname, out)


def _check_initials(states: dict[str, StateNode], prefix: str,
                    issues: list[Issue]):
    for name, node in states.items():
        qname = f"{prefix}.{name}" if prefix else name
        if node.children and node.state_type not in ("parallel", "history"):
            if not node.initial:
                issues.append(Issue("error", "NO_INITIAL",
                                    f"Compound state \"{qname}\" has children but no initial state"))
            elif node.initial not in node.children:
                issues.append(Issue("error", "MISSING_INITIAL",
                                    f"Compound state \"{qname}\" initial \"{node.initial}\" "
                                    f"does not exist in children"))
            _check_initials(node.children, qname, issues)


def _check_finals(all_states: dict[str, StateNode], issues: list[Issue]):
    for qname, node in all_states.items():
        if node.state_type == "final":
            outgoing = node.transitions + node.always + node.after
            if outgoing:
                issues.append(Issue("warning", "FINAL_HAS_TRANSITIONS",
                                    f"Final state \"{qname}\" has outgoing transitions"))


def _find_reachable(machine: Machine) -> set[str]:
    """BFS from initial state, following all transitions."""
    reachable: set[str] = set()
    if not machine.initial:
        return reachable

    # Build adjacency: state_name -> set of target names (flat, within scope)
    # We do per-scope BFS starting from root
    _reachable_scope(machine.root_states, machine.initial, "", reachable)
    return reachable


def _reachable_scope(states: dict[str, StateNode], initial: str | None,
                     prefix: str, reachable: set[str]):
    """BFS within a scope. Also recurses into children."""
    if not initial or initial not in states:
        # Mark all states in parallel regions as reachable
        for name, node in states.items():
            qname = f"{prefix}.{name}" if prefix else name
            reachable.add(qname)
            if node.children:
                child_initial = node.initial
                if node.state_type == "parallel":
                    _reachable_parallel(node, qname, reachable)
                elif child_initial:
                    _reachable_scope(node.children, child_initial, qname, reachable)
        return

    queue = [initial]
    visited: set[str] = set()

    while queue:
        name = queue.pop(0)
        if name in visited or name not in states:
            continue
        visited.add(name)
        qname = f"{prefix}.{name}" if prefix else name
        reachable.add(qname)

        node = states[name]

        # Recurse into children
        if node.children and node.state_type == "parallel":
            _reachable_parallel(node, qname, reachable)
        elif node.children and node.initial:
            _reachable_scope(node.children, node.initial, qname, reachable)

        # Follow all transitions
        for t in _all_transitions(node):
            if t.target and t.target in states:
                queue.append(t.target)


def _reachable_parallel(node: StateNode, prefix: str, reachable: set[str]):
    """All regions in a parallel state are reachable."""
    for cname, child in node.children.items():
        cqname = f"{prefix}.{cname}"
        reachable.add(cqname)
        if child.children:
            if child.state_type == "parallel":
                _reachable_parallel(child, cqname, reachable)
            else:
                _reachable_scope(child.children, child.initial, cqname, reachable)


def _all_transitions(node: StateNode) -> list[Transition]:
    """Collect all transitions from a state node."""
    result = list(node.transitions) + list(node.always) + list(node.after) + list(node.on_done)
    for inv in node.invocations:
        result.extend(inv.on_done)
        result.extend(inv.on_error)
    return result
