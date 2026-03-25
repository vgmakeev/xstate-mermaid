"""Tests for static analysis and runtime validation."""
import json
import subprocess
import sys
import pytest
from xstate_dsl import parse, to_xstate, validate_static
from xstate_dsl.validate import Issue


class TestStaticValidation:
    def test_valid_machine(self):
        m = parse("""
stateDiagram-v2
    %% machine: test
    [*] --> idle
    idle --> active : GO
    active --> idle : BACK
""")
        issues = validate_static(m)
        errors = [i for i in issues if i.level == "error"]
        assert len(errors) == 0

    def test_empty_machine(self):
        m = parse("""
stateDiagram-v2
    %% machine: empty
""")
        issues = validate_static(m)
        assert any(i.code == "EMPTY_MACHINE" for i in issues)

    def test_missing_initial_in_compound(self):
        m = parse("""
stateDiagram-v2
    %% machine: test
    [*] --> parent

    state parent {
        state child1 {
        }
    }
""")
        issues = validate_static(m)
        assert any(i.code == "NO_INITIAL" and "parent" in i.message for i in issues)

    def test_unreachable_state(self):
        m = parse("""
stateDiagram-v2
    %% machine: test
    [*] --> a
    a --> b : GO

    state orphan {
    }
""")
        issues = validate_static(m)
        assert any(i.code == "UNREACHABLE_STATE" and "orphan" in i.message for i in issues)

    def test_no_unreachable_in_valid_machine(self):
        m = parse("""
stateDiagram-v2
    %% machine: test
    [*] --> a
    a --> b : GO
    b --> a : BACK
""")
        issues = validate_static(m)
        unreachable = [i for i in issues if i.code == "UNREACHABLE_STATE"]
        assert len(unreachable) == 0

    def test_parallel_all_reachable(self):
        m = parse("""
stateDiagram-v2
    %% machine: test
    [*] --> par

    state par {
        state r1 {
            [*] --> a
            a --> b : GO
        }
        --
        state r2 {
            [*] --> c
            c --> d : GO
        }
    }
""")
        issues = validate_static(m)
        unreachable = [i for i in issues if i.code == "UNREACHABLE_STATE"]
        assert len(unreachable) == 0

    def test_final_with_outgoing(self):
        m = parse("""
stateDiagram-v2
    %% machine: test
    [*] --> a
    a --> done : GO
    done --> a : BACK
    done --> [*]
""")
        issues = validate_static(m)
        assert any(i.code == "FINAL_HAS_TRANSITIONS" for i in issues)

    def test_nested_reachability(self):
        m = parse("""
stateDiagram-v2
    %% machine: test
    [*] --> outer

    state outer {
        [*] --> inner
        inner --> done : FINISH

        state inner {
            [*] --> working
            working --> waiting : PAUSE
            waiting --> working : RESUME
        }
    }
""")
        issues = validate_static(m)
        unreachable = [i for i in issues if i.code == "UNREACHABLE_STATE"]
        assert len(unreachable) == 0

    def test_orderflow_valid(self):
        text = open("orderflow.md").read()
        m = parse(text)
        issues = validate_static(m)
        errors = [i for i in issues if i.level == "error"]
        assert len(errors) == 0


class TestCLIValidate:
    def test_cli_validate_text(self):
        r = subprocess.run(
            [sys.executable, "-m", "xstate_dsl", "validate", "orderflow.md", "--static-only"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        assert "all checks passed" in r.stdout

    def test_cli_validate_json(self):
        r = subprocess.run(
            [sys.executable, "-m", "xstate_dsl", "validate", "orderflow.md",
             "--static-only", "--format", "json"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["valid"] is True

    def test_cli_validate_broken(self):
        r = subprocess.run(
            [sys.executable, "-m", "xstate_dsl", "validate", "-", "--static-only"],
            input="""
stateDiagram-v2
    %% machine: broken
    [*] --> a

    state compound {
        state orphan {
        }
    }
""",
            capture_output=True, text=True,
        )
        assert r.returncode == 1
        assert "ERROR" in r.stdout

    def test_cli_validate_with_runtime(self):
        r = subprocess.run(
            [sys.executable, "-m", "xstate_dsl", "validate", "orderflow.md"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        assert "createMachine" in r.stdout or "RUNTIME_SKIP" in r.stdout

    def test_cli_validate_with_scenarios(self):
        r = subprocess.run(
            [sys.executable, "-m", "xstate_dsl", "validate",
             "test_xstate_runtime/traffic.md",
             "--scenarios", "test_xstate_runtime/scenario_traffic.json"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        assert "5/5 passed" in r.stdout

    def test_cli_strict_mode(self):
        r = subprocess.run(
            [sys.executable, "-m", "xstate_dsl", "validate", "-",
             "--static-only", "--strict"],
            input="""
stateDiagram-v2
    %% machine: test
    [*] --> a

    state orphan {
    }
""",
            capture_output=True, text=True,
        )
        # Has warnings (unreachable) → --strict makes it fail
        assert r.returncode == 1
