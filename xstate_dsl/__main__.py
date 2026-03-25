#!/usr/bin/env python3
"""CLI for XState DSL converter.

Usage:
    python -m xstate_dsl dsl2xstate input.dsl [-o output.json]
    python -m xstate_dsl xstate2dsl input.json [-o output.dsl]
    python -m xstate_dsl roundtrip input.dsl    # DSL → XState → DSL (verify)
"""
import argparse
import json
import sys
from . import parse, to_xstate, to_dsl


def main():
    p = argparse.ArgumentParser(description="XState v5 ↔ DSL converter")
    p.add_argument("command", choices=["dsl2xstate", "xstate2dsl", "roundtrip"])
    p.add_argument("input", help="Input file (- for stdin)")
    p.add_argument("-o", "--output", help="Output file (default: stdout)")
    args = p.parse_args()

    text = sys.stdin.read() if args.input == "-" else open(args.input).read()

    if args.command == "dsl2xstate":
        machine = parse(text)
        result = json.dumps(to_xstate(machine), indent=2, default=str)
    elif args.command == "xstate2dsl":
        config = json.loads(text)
        result = to_dsl(config)
    elif args.command == "roundtrip":
        machine = parse(text)
        config = to_xstate(machine)
        result = to_dsl(config)
    else:
        p.error(f"Unknown command: {args.command}")

    if args.output:
        with open(args.output, "w") as f:
            f.write(result)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(result)


if __name__ == "__main__":
    main()
