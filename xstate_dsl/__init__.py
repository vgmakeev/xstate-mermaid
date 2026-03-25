"""Mermaid stateDiagram-v2 ↔ XState v5 bidirectional converter & validator.

Usage:
    from xstate_dsl import parse, to_xstate, to_mermaid, validate_static

    # Mermaid → XState config
    machine = parse(mermaid_text)
    config = to_xstate(machine)

    # XState config → Mermaid
    mermaid_text = to_mermaid(xstate_config)

    # Validate
    issues = validate_static(machine)
"""
from .parser import parse
from .to_xstate import to_xstate
from .to_mermaid import to_mermaid
from .validate import validate_static

__all__ = ["parse", "to_xstate", "to_mermaid", "validate_static"]
