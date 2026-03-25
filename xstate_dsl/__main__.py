#!/usr/bin/env python3
"""CLI for Mermaid ↔ XState v5 converter.

Usage:
    xstate-dsl mermaid2xstate input.md [-o output.json]
    xstate-dsl xstate2mermaid input.json [-o output.md]
    xstate-dsl roundtrip input.md
    xstate-dsl validate input.md [--static-only] [--scenarios file] [--strict]
"""
import argparse
import json
import sys
from . import parse, to_xstate, to_mermaid


def main():
    p = argparse.ArgumentParser(
        prog="xstate-dsl",
        description="Mermaid stateDiagram-v2 ↔ XState v5 converter & validator",
    )
    sub = p.add_subparsers(dest="command")

    # mermaid2xstate
    m2x = sub.add_parser("mermaid2xstate", help="Mermaid → XState v5 JSON")
    m2x.add_argument("input", help="Input file (- for stdin)")
    m2x.add_argument("-o", "--output", help="Output file (default: stdout)")

    # xstate2mermaid
    x2m = sub.add_parser("xstate2mermaid", help="XState v5 JSON → Mermaid")
    x2m.add_argument("input", help="Input file (- for stdin)")
    x2m.add_argument("-o", "--output", help="Output file (default: stdout)")

    # roundtrip
    rt = sub.add_parser("roundtrip", help="Mermaid → XState → Mermaid (verify losslessness)")
    rt.add_argument("input", help="Input file (- for stdin)")
    rt.add_argument("-o", "--output", help="Output file (default: stdout)")

    # validate
    val = sub.add_parser("validate", help="Validate a Mermaid statechart")
    val.add_argument("input", help="Mermaid input file (- for stdin)")
    val.add_argument("--static-only", action="store_true",
                     help="Skip runtime validation (no Node.js needed)")
    val.add_argument("--scenarios", help="YAML/JSON file with test scenarios")
    val.add_argument("--strict", action="store_true",
                     help="Treat warnings as errors (exit code 1)")
    val.add_argument("--format", choices=["text", "json"], default="text",
                     help="Output format (default: text)")

    args = p.parse_args()
    if not args.command:
        p.print_help()
        sys.exit(1)

    if args.command == "validate":
        cmd_validate(args)
        return

    text = sys.stdin.read() if args.input == "-" else open(args.input).read()

    if args.command == "mermaid2xstate":
        machine = parse(text)
        result = json.dumps(to_xstate(machine), indent=2, default=str)
    elif args.command == "xstate2mermaid":
        config = json.loads(text)
        result = to_mermaid(config)
    elif args.command == "roundtrip":
        machine = parse(text)
        config = to_xstate(machine)
        result = to_mermaid(config)

    if args.output:
        with open(args.output, "w") as f:
            f.write(result)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(result)


def cmd_validate(args):
    from .validate import validate_static, Issue
    from .runtime import check_runtime_available, validate_runtime, run_scenarios, load_scenarios

    text = sys.stdin.read() if args.input == "-" else open(args.input).read()
    machine = parse(text)
    config = to_xstate(machine)

    all_issues: list[Issue] = []
    scenario_results: list[dict] = []

    # 1. Static analysis
    all_issues.extend(validate_static(machine))

    # 2. Runtime validation
    if not args.static_only:
        ok, msg = check_runtime_available()
        if ok:
            all_issues.extend(validate_runtime(config))
        else:
            all_issues.append(Issue("info", "RUNTIME_SKIP", msg))

    # 3. Scenarios
    if args.scenarios:
        scenarios = load_scenarios(args.scenarios)
        scenario_results = run_scenarios(config, scenarios)

    # Output
    if args.format == "json":
        _output_json(all_issues, scenario_results)
    else:
        _output_text(args.input, all_issues, scenario_results)

    # Exit code
    errors = [i for i in all_issues if i.level == "error"]
    warnings = [i for i in all_issues if i.level == "warning"]
    failed_scenarios = [s for s in scenario_results if not s.get("pass", True)]

    if errors or failed_scenarios:
        sys.exit(1)
    if args.strict and warnings:
        sys.exit(1)


def _output_text(filename: str, issues, scenario_results):
    from .validate import Issue

    print(f"\nValidating: {filename}\n")

    # Group by category
    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]
    infos = [i for i in issues if i.level == "info"]

    # Static analysis
    static = [i for i in issues if not i.code.startswith("RUNTIME")]
    runtime = [i for i in issues if i.code.startswith("RUNTIME")]

    if static:
        print("Static Analysis")
        for i in static:
            icon = {"error": "ERROR", "warning": "WARN ", "info": "OK   "}[i.level]
            print(f"  {icon}  {i.code:22s} {i.message}")
    else:
        print("Static Analysis")
        print("  OK     No issues found")

    if runtime:
        print("\nRuntime Validation (XState v5)")
        for i in runtime:
            icon = {"error": "ERROR", "warning": "WARN ", "info": "OK   "}[i.level]
            print(f"  {icon}  {i.message}")

    if scenario_results:
        passed = sum(1 for s in scenario_results if s.get("pass"))
        total = len(scenario_results)
        print(f"\nScenarios ({passed}/{total} passed)")
        for s in scenario_results:
            if s.get("error") and not s.get("send"):
                print(f"  ERROR  {s['error']}")
                continue
            step = s.get("step", "?")
            send = s.get("send", s.get("type", ""))
            expected = s.get("expected", "")
            actual = s.get("actual", "")
            ok = "PASS" if s.get("pass") else "FAIL"
            if s.get("type") == "initial":
                print(f"  [{step}]  initial → expected \"{expected}\" → got \"{actual}\"  {ok}")
            else:
                print(f"  [{step}]  send {send:16s} → expected \"{expected}\" → got \"{actual}\"  {ok}")

    # Summary
    n_err = len(errors)
    n_warn = len(warnings)
    n_fail = sum(1 for s in scenario_results if not s.get("pass", True))
    parts = []
    if n_err:
        parts.append(f"{n_err} error{'s' if n_err > 1 else ''}")
    if n_warn:
        parts.append(f"{n_warn} warning{'s' if n_warn > 1 else ''}")
    if n_fail:
        parts.append(f"{n_fail} scenario failure{'s' if n_fail > 1 else ''}")
    if not parts:
        parts.append("all checks passed")

    print(f"\nResult: {', '.join(parts)}\n")


def _output_json(issues, scenario_results):
    data = {
        "issues": [{"level": i.level, "code": i.code, "message": i.message} for i in issues],
        "scenarios": scenario_results,
        "valid": not any(i.level == "error" for i in issues),
    }
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
