#!/usr/bin/env python3
"""Generate XState v5 configs from Mermaid inputs for runtime validation."""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from xstate_dsl import parse, to_xstate

MACHINES = {
    "trafficLight": """
stateDiagram-v2
    %% machine: trafficLight

    [*] --> red
    red --> green : TIMER
    green --> yellow : TIMER
    yellow --> red : TIMER
""",
    "auth": """
stateDiagram-v2
    %% machine: auth

    [*] --> idle
    idle --> authenticating : LOGIN [hasCredentials] / setLoading
    idle --> idle : LOGIN [else] / showError

    authenticating --> authenticated : done / assignUser
    authenticating --> failed : error / assignError
    authenticating --> idle : after 10000

    state authenticating {
        %% invoke: authService [id: auth]
    }

    state authenticated {
        %% type: final
        %% entry: notifySuccess
    }

    failed --> authenticating : RETRY
""",
    "toggle": """
stateDiagram-v2
    %% machine: toggle

    [*] --> inactive
    inactive --> active : TOGGLE
    active --> inactive : TOGGLE
""",
    "nested": """
stateDiagram-v2
    %% machine: nested

    [*] --> parent

    state parent {
        [*] --> child1
        child1 --> child2 : NEXT
        child2 --> child1 : BACK
    }
""",
    "parallel": """
stateDiagram-v2
    %% machine: parallel

    [*] --> dashboard

    state dashboard {
        state upload {
            [*] --> uploadIdle
            uploadIdle --> uploading : START_UPLOAD
            uploading --> uploadDone : UPLOAD_COMPLETE
            uploadDone --> [*]
        }
        --
        state mode {
            [*] --> light
            light --> dark : TOGGLE_MODE
            dark --> light : TOGGLE_MODE
        }
    }
""",
    "guarded": """
stateDiagram-v2
    %% machine: guarded

    [*] --> idle
    idle --> success : SUBMIT [isValid] / save
    idle --> error : SUBMIT [else] / showErrors
    success --> [*]
""",
    "delayed": """
stateDiagram-v2
    %% machine: delayed

    [*] --> waiting
    waiting --> timeout : after 3000
    waiting --> done : COMPLETE
""",
    "always": """
stateDiagram-v2
    %% machine: always

    [*] --> checking
    checking --> valid : always [isReady]
    checking --> waiting : always [else]
    valid --> [*]
    waiting --> checking : RETRY
""",
    "history": """
stateDiagram-v2
    %% machine: history

    [*] --> editor
    editor --> settings : OPEN_SETTINGS
    settings --> editor : CLOSE

    state editor {
        [*] --> draft
        draft --> preview : PREVIEW
        preview --> draft : EDIT

        state hist {
            %% type: history
            %% target: draft
        }
    }
""",
    "selfTransition": """
stateDiagram-v2
    %% machine: selfTransition

    [*] --> counter
    counter --> counter : INCREMENT / increment
    counter --> counter : RESET / reset @reenter
    counter --> done : FINISH
    done --> [*]
""",
    "multiGuard": """
stateDiagram-v2
    %% machine: multiGuard

    [*] --> idle
    idle --> premium : SUBMIT [isValid, isPremium] / processPremium
    idle --> standard : SUBMIT [isValid] / processStandard
    idle --> idle : SUBMIT [else] / showError
""",
}


def strip_raw(obj):
    """Recursively replace __raw__ markers with plain strings for JS consumption."""
    if isinstance(obj, dict):
        if "__raw__" in obj:
            return obj["__raw__"]
        return {k: strip_raw(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [strip_raw(v) for v in obj]
    return obj


def main():
    configs = {}
    for name, mermaid in MACHINES.items():
        m = parse(mermaid)
        config = to_xstate(m)
        configs[name] = strip_raw(config)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs.json")
    with open(out_path, "w") as f:
        json.dump(configs, f, indent=2, default=str)
    print(f"Generated {len(configs)} configs → {out_path}")


if __name__ == "__main__":
    main()
