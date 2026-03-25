"""XState v5 Compact DSL — bidirectional converter.

Usage:
    from xstate_dsl import parse, to_xstate, to_dsl

    # DSL → XState config
    machine = parse(dsl_text)
    config = to_xstate(machine)

    # XState config → DSL
    dsl_text = to_dsl(xstate_config)
"""
from .parser import parse
from .to_xstate import to_xstate
from .to_dsl import to_dsl

__all__ = ["parse", "to_xstate", "to_dsl"]
