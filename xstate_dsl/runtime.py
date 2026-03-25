"""XState v5 runtime validation via Node.js subprocess."""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
from typing import Any

from .validate import Issue

_RUNTIME_DIR = os.path.join(os.path.dirname(__file__), "_runtime")
_VALIDATE_SCRIPT = os.path.join(_RUNTIME_DIR, "validate_machine.mjs")


def strip_raw(obj: Any) -> Any:
    """Recursively replace __raw__ markers with plain strings for JS consumption."""
    if isinstance(obj, dict):
        if "__raw__" in obj:
            return obj["__raw__"]
        return {k: strip_raw(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [strip_raw(v) for v in obj]
    return obj


def check_runtime_available() -> tuple[bool, str]:
    """Check if Node.js and xstate are available."""
    node = shutil.which("node")
    if not node:
        return False, "node not found in PATH — install Node.js for runtime validation"

    try:
        r = subprocess.run(
            [node, "-e", "import('xstate').then(()=>process.exit(0)).catch(()=>process.exit(1))"],
            capture_output=True, timeout=10,
            cwd=_RUNTIME_DIR,
        )
        if r.returncode != 0:
            return False, (
                "xstate package not found — run: "
                "npm install xstate --prefix " + _RUNTIME_DIR
            )
    except subprocess.TimeoutExpired:
        return False, "node timed out checking xstate availability"

    return True, "ok"


def validate_runtime(xstate_config: dict) -> list[Issue]:
    """Run XState v5 createMachine + createActor validation via Node.js."""
    payload = json.dumps({"config": strip_raw(xstate_config)})

    try:
        r = subprocess.run(
            ["node", _VALIDATE_SCRIPT],
            input=payload, capture_output=True, text=True,
            timeout=15, cwd=_RUNTIME_DIR,
        )
    except subprocess.TimeoutExpired:
        return [Issue("error", "RUNTIME_TIMEOUT", "XState runtime validation timed out")]
    except FileNotFoundError:
        return [Issue("error", "NODE_NOT_FOUND", "node executable not found")]

    if r.returncode != 0:
        stderr = r.stderr.strip()
        return [Issue("error", "RUNTIME_CRASH",
                       f"Runtime validation crashed: {stderr[:500]}")]

    try:
        result = json.loads(r.stdout)
    except json.JSONDecodeError:
        return [Issue("error", "RUNTIME_PARSE",
                       f"Could not parse runtime output: {r.stdout[:300]}")]

    issues: list[Issue] = []
    for err in result.get("errors", []):
        issues.append(Issue("error", "RUNTIME_ERROR", err))
    for warn in result.get("warnings", []):
        issues.append(Issue("warning", "RUNTIME_WARNING", warn))
    if result.get("valid"):
        issues.append(Issue("info", "RUNTIME_OK",
                            f"createMachine() + createActor() succeeded — "
                            f"initial state: \"{result.get('initialState', '?')}\""))
    return issues


def run_scenarios(xstate_config: dict, scenarios: list[dict]) -> list[dict]:
    """Run scenario traces through XState runtime. Returns list of step results."""
    payload = json.dumps({
        "config": strip_raw(xstate_config),
        "scenarios": scenarios,
    })

    try:
        r = subprocess.run(
            ["node", _VALIDATE_SCRIPT],
            input=payload, capture_output=True, text=True,
            timeout=15, cwd=_RUNTIME_DIR,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return [{"error": "Runtime not available"}]

    if r.returncode != 0:
        return [{"error": f"Runtime crashed: {r.stderr.strip()[:300]}"}]

    try:
        result = json.loads(r.stdout)
    except json.JSONDecodeError:
        return [{"error": f"Could not parse output: {r.stdout[:300]}"}]

    return result.get("scenarios", [])


def load_scenarios(path: str) -> list[dict]:
    """Load scenarios from a YAML or JSON file.

    Returns a list of scenario objects, each with "steps" array and optional "initial".
    Input can be:
      - A single scenario: {"initial": "red", "steps": [...]}
      - A list of scenarios: [{"steps": [...]}, {"steps": [...]}]
      - A bare list of steps: [{"send": "X", "expect": "Y"}, ...]
    """
    text = open(path).read()

    if path.endswith((".yaml", ".yml")):
        try:
            import yaml
            data = yaml.safe_load(text)
        except ImportError:
            print("Warning: PyYAML not installed, trying JSON parse", file=sys.stderr)
            data = json.loads(text)
    else:
        data = json.loads(text)

    if isinstance(data, dict):
        # Single scenario object with "steps"
        return [data]
    if isinstance(data, list):
        # Check if it's a list of scenarios or a bare list of steps
        if data and "send" in data[0]:
            # Bare step list → wrap as single scenario
            return [{"steps": data}]
        return data
    return []
