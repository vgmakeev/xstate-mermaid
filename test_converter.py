"""Tests for bidirectional XState DSL converter."""
import json
from xstate_dsl import parse, to_xstate, to_dsl


def test_basic_machine():
    """Parse a simple 3-state machine."""
    dsl = """
machine: trafficLight
context: { color: "red" }

state red [initial]
  TIMER -> green

state green
  TIMER -> yellow

state yellow
  TIMER -> red
"""
    m = parse(dsl)
    assert m.id == "trafficLight"
    assert "red" in m.root_states
    assert "green" in m.root_states
    assert "yellow" in m.root_states
    assert m.initial == "red"

    t = m.root_states["red"].transitions[0]
    assert t.event == "TIMER"
    assert t.target == "green"

    config = to_xstate(m)
    assert config["config"]["id"] == "trafficLight"
    assert config["config"]["states"]["red"]["on"]["TIMER"] == "green"
    print("  ✓ basic machine")


def test_guards():
    """Parse guard expressions."""
    dsl = """
machine: auth

state idle
  LOGIN [hasCredentials] / validate -> checking
  LOGIN [else] / showError
"""
    m = parse(dsl)
    t0 = m.root_states["idle"].transitions[0]
    assert t0.guards is not None
    assert t0.guards.guard.name == "hasCredentials"
    assert t0.target == "checking"

    t1 = m.root_states["idle"].transitions[1]
    assert t1.guards is None  # [else] → None
    print("  ✓ guards")


def test_compound_guards():
    """Parse AND, OR, NOT guards."""
    dsl = """
machine: test

state s1
  EV1 [a, b] -> s2
  EV2 [x | y] -> s3
  EV3 [!z] -> s4
"""
    m = parse(dsl)
    t0 = m.root_states["s1"].transitions[0]
    assert t0.guards.op == "and"
    assert len(t0.guards.children) == 2

    t1 = m.root_states["s1"].transitions[1]
    assert t1.guards.op == "or"

    t2 = m.root_states["s1"].transitions[2]
    assert t2.guards.guard.negated
    print("  ✓ compound guards")


def test_actions():
    """Parse various action forms."""
    dsl = """
machine: test

state s1
  entry: startSpinner, logEnter
  exit: stopSpinner
  CLICK / assign({ count: inc }) -> s2
  SEND / sendTo(parent, { type: "DONE" })
"""
    m = parse(dsl)
    s = m.root_states["s1"]
    assert len(s.entry) == 2
    assert s.entry[0].name == "startSpinner"
    assert s.exit[0].name == "stopSpinner"

    t0 = s.transitions[0]
    assert t0.actions[0].kind == "assign"

    t1 = s.transitions[1]
    assert t1.actions[0].kind == "sendTo"
    print("  ✓ actions")


def test_invoke():
    """Parse invoke with onDone/onError."""
    dsl = """
machine: loader

state loading
  invoke: fetchData [id: fetcher, input: { url: context.url }]
    done / assignResult -> success
    error / assignError -> failure

state success [type: final]
state failure
"""
    m = parse(dsl)
    s = m.root_states["loading"]
    assert len(s.invocations) == 1
    inv = s.invocations[0]
    assert inv.src == "fetchData"
    assert inv.id == "fetcher"
    assert len(inv.on_done) == 1
    assert len(inv.on_error) == 1
    assert inv.on_done[0].target == "success"

    config = to_xstate(m)
    inv_cfg = config["config"]["states"]["loading"]["invoke"]
    assert inv_cfg["src"] == "fetchData"
    assert inv_cfg["id"] == "fetcher"
    print("  ✓ invoke")


def test_always():
    """Parse always (eventless) transitions."""
    dsl = """
machine: test

state checking
  always [isValid] / process -> valid
  always [else] -> invalid

state valid [type: final]
state invalid
"""
    m = parse(dsl)
    s = m.root_states["checking"]
    assert len(s.always) == 2
    assert s.always[0].guards.guard.name == "isValid"
    assert s.always[0].target == "valid"
    assert s.always[1].guards is None

    config = to_xstate(m)
    always = config["config"]["states"]["checking"]["always"]
    assert len(always) == 2
    print("  ✓ always")


def test_after():
    """Parse after (delayed) transitions."""
    dsl = """
machine: test

state waiting
  after: 3000 -> timeout
  after: 5000 [isImpatient] / warn -> timeout

state timeout
"""
    m = parse(dsl)
    s = m.root_states["waiting"]
    assert len(s.after) == 2
    assert s.after[0].delay == 3000
    assert s.after[0].target == "timeout"
    assert s.after[1].delay == 5000
    assert s.after[1].guards is not None

    config = to_xstate(m)
    after = config["config"]["states"]["waiting"]["after"]
    assert 3000 in after
    assert 5000 in after
    print("  ✓ after")


def test_nested_states():
    """Parse hierarchical states."""
    dsl = """
machine: editor

state active [initial: idle]

  state idle
    START -> running

  state running [initial: fetching]
    CANCEL -> idle

    state fetching
      LOADED -> processing

    state processing
      DONE -> idle

state inactive
"""
    m = parse(dsl)
    assert "active" in m.root_states
    assert "inactive" in m.root_states
    active = m.root_states["active"]
    assert active.initial == "idle"
    assert "idle" in active.children
    assert "running" in active.children
    running = active.children["running"]
    assert "fetching" in running.children
    assert "processing" in running.children

    config = to_xstate(m)
    active_cfg = config["config"]["states"]["active"]
    assert "idle" in active_cfg["states"]
    assert "running" in active_cfg["states"]
    print("  ✓ nested states")


def test_parallel():
    """Parse parallel states with regions."""
    dsl = """
machine: dashboard

state main [type: parallel]

  region notifications [initial: idle]
    state idle
      NEW -> showing
    state showing
      after: 3000 -> idle

  region feed [initial: polling]
    state polling
      PAUSE -> paused
    state paused
      RESUME -> polling
"""
    m = parse(dsl)
    s = m.root_states["main"]
    assert s.state_type == "parallel"
    assert "notifications" in s.children
    assert "feed" in s.children
    assert "idle" in s.children["notifications"].children
    assert "polling" in s.children["feed"].children

    config = to_xstate(m)
    main_cfg = config["config"]["states"]["main"]
    assert main_cfg["type"] == "parallel"
    assert "notifications" in main_cfg["states"]
    print("  ✓ parallel states")


def test_history():
    """Parse history states."""
    dsl = """
machine: test

state editor [initial: draft]
  state draft
    PUBLISH -> published
  state published
    UNPUBLISH -> hist
  state hist [type: history.deep]
    target: draft
"""
    m = parse(dsl)
    hist = m.root_states["editor"].children["hist"]
    assert hist.state_type == "history"
    assert hist.history_type == "deep"
    assert hist.history_target == "draft"

    config = to_xstate(m)
    hist_cfg = config["config"]["states"]["editor"]["states"]["hist"]
    assert hist_cfg["type"] == "history"
    assert hist_cfg["history"] == "deep"
    assert hist_cfg["target"] == "draft"
    print("  ✓ history states")


def test_guarded_branches():
    """Parse multi-branch event with guards."""
    dsl = """
machine: form

state editing
  SUBMIT
    [isValid, hasPermission] / save -> success
    [isValid] / queueReview -> pending
    [else] / showErrors -> editing
"""
    m = parse(dsl)
    s = m.root_states["editing"]
    assert len(s.transitions) == 3
    assert s.transitions[0].event == "SUBMIT"
    assert s.transitions[0].guards.op == "and"
    assert s.transitions[1].event == "SUBMIT"
    assert s.transitions[2].guards is None  # else
    print("  ✓ guarded branches")


def test_reenter():
    """Parse reenter transitions."""
    dsl = """
machine: test

state s1
  REFRESH / reload ->@ s1
"""
    m = parse(dsl)
    t = m.root_states["s1"].transitions[0]
    assert t.reenter
    assert t.target == "s1"

    config = to_xstate(m)
    t_cfg = config["config"]["states"]["s1"]["on"]["REFRESH"]
    assert t_cfg["reenter"] is True
    print("  ✓ reenter")


def test_tags_and_meta():
    """Parse tags and description."""
    dsl = """
machine: test

state idle [tags: ready, waiting] [description: "Initial state"]
  GO -> active

state active
"""
    m = parse(dsl)
    s = m.root_states["idle"]
    assert s.tags == ["ready", "waiting"]
    assert s.description == "Initial state"

    config = to_xstate(m)
    s_cfg = config["config"]["states"]["idle"]
    assert s_cfg["tags"] == ["ready", "waiting"]
    assert s_cfg["description"] == "Initial state"
    print("  ✓ tags and meta")


def test_wildcard():
    """Parse wildcard transitions."""
    dsl = """
machine: test

state s1
  GO -> s2

state s2
  BACK -> s1

* [isError] / logError -> s1
"""
    m = parse(dsl)
    assert len(m.wildcard_transitions) == 1
    wt = m.wildcard_transitions[0]
    assert wt.event == "*"
    assert wt.guards.guard.name == "isError"

    config = to_xstate(m)
    assert "*" in config["config"]["on"]
    print("  ✓ wildcard")


def test_xstate_to_dsl():
    """Convert XState config to DSL and back."""
    xstate_config = {
        "id": "toggle",
        "initial": "inactive",
        "states": {
            "inactive": {
                "on": {
                    "TOGGLE": "active"
                }
            },
            "active": {
                "on": {
                    "TOGGLE": "inactive"
                },
                "after": {
                    5000: "inactive"
                }
            }
        }
    }

    dsl_text = to_dsl(xstate_config)
    assert "machine: toggle" in dsl_text
    assert "TOGGLE -> active" in dsl_text
    assert "TOGGLE -> inactive" in dsl_text
    assert "after: 5000 -> inactive" in dsl_text

    # Round-trip: DSL → parse → to_xstate
    m = parse(dsl_text)
    config = to_xstate(m)
    assert config["config"]["id"] == "toggle"
    assert "inactive" in config["config"]["states"]
    assert "active" in config["config"]["states"]
    print("  ✓ xstate → dsl round-trip")


def test_xstate_complex_to_dsl():
    """Convert a complex XState config to DSL."""
    xstate_config = {
        "id": "auth",
        "initial": "idle",
        "states": {
            "idle": {
                "on": {
                    "LOGIN": {
                        "target": "authenticating",
                        "guard": "hasCredentials",
                        "actions": "setLoading"
                    }
                }
            },
            "authenticating": {
                "invoke": {
                    "src": "authService",
                    "id": "auth",
                    "onDone": {
                        "target": "authenticated",
                        "actions": "assignUser"
                    },
                    "onError": [
                        {
                            "target": "idle",
                            "guard": "isRetryable",
                            "actions": "incrementRetry"
                        },
                        {
                            "target": "failed",
                            "actions": "assignError"
                        }
                    ]
                },
                "after": {
                    10000: "idle"
                }
            },
            "authenticated": {
                "type": "final",
                "entry": "notifySuccess"
            },
            "failed": {
                "on": {
                    "RETRY": "authenticating"
                }
            }
        }
    }

    dsl_text = to_dsl(xstate_config)
    assert "machine: auth" in dsl_text
    assert "invoke: authService" in dsl_text
    assert "done" in dsl_text
    assert "error" in dsl_text
    assert "after: 10000" in dsl_text
    assert "type: final" in dsl_text

    # Round-trip
    m = parse(dsl_text)
    assert m.id == "auth"
    assert len(m.root_states["authenticating"].invocations) == 1
    print("  ✓ complex xstate → dsl")


def test_full_orderflow():
    """Test the full order flow example from the spec."""
    dsl = """
machine: orderFlow
version: 1.0.0
context: {
  items: [],
  total: 0,
  error: null,
  retries: 0
}
input: { userId: string, cartId: string }

state idle [initial] [tags: ready] [description: "Waiting for order"]
  entry: resetForm
  exit: clearErrors
  SUBMIT [hasItems, isAuthed] / validateCart -> validating
  SUBMIT [else] / showErrors

state validating
  invoke: validateOrder [id: validator, input: { items: context.items }]
    done [isValid] / assignValidated -> confirming
    done [else] / assignErrors -> editing
    error / assignError -> editing
  after: 10000 -> editing

state editing
  UPDATE_ITEM / assignItem
  REMOVE_ITEM / removeItem, recalcTotal
  SUBMIT [hasItems] -> validating
  CANCEL / clearDraft -> idle

state confirming
  CONFIRM / setProcessing -> processing
  BACK -> editing
  CANCEL -> idle

state processing [type: parallel]

  region payment [initial: charging]
    state charging
      invoke: processPayment [id: paymentSvc]
        done / assignPaymentResult -> charged
        error [isRetryable] / incrementRetry -> retrying
        error [else] / assignError -> failed
    state retrying
      after: 2000 -> charging
      always [retries >= 3] -> failed
    state charged [type: final]
    state failed

  region inventory [initial: reserving]
    state reserving
      invoke: reserveInventory
        done / assignReservation -> reserved
        error -> reserveFailed
    state reserved [type: final]
    state reserveFailed
      RETRY_RESERVE -> reserving

  done.state -> fulfilling

state fulfilling
  invoke: createShipment
    done / assignTracking -> complete
    error / assignError -> supportNeeded

state complete [type: final]
  entry: notifyComplete

state supportNeeded
  RESOLVED -> fulfilling
  CANCEL -> cancelled

state cancelled [type: final]
  entry: rollbackAll
"""
    m = parse(dsl)
    assert m.id == "orderFlow"
    assert m.version == "1.0.0"
    assert len(m.root_states) == 9

    # Check parallel
    proc = m.root_states["processing"]
    assert proc.state_type == "parallel"
    assert "payment" in proc.children
    assert "inventory" in proc.children
    assert len(proc.on_done) == 1

    # Check invoke chains
    charging = proc.children["payment"].children["charging"]
    assert len(charging.invocations) == 1
    assert len(charging.invocations[0].on_done) == 1
    assert len(charging.invocations[0].on_error) == 2

    # Full round-trip
    config = to_xstate(m)
    dsl2 = to_dsl(config)
    m2 = parse(dsl2)
    assert m2.id == "orderFlow"
    assert len(m2.root_states) >= 8
    assert m2.root_states["processing"].state_type == "parallel"
    print("  ✓ full orderFlow round-trip")


def test_done_state():
    """Parse done.state transitions."""
    dsl = """
machine: test

state main [type: parallel]

  region a [initial: s1]
    state s1
      GO -> s2
    state s2 [type: final]

  region b [initial: s3]
    state s3
      GO -> s4
    state s4 [type: final]

  done.state -> complete

state complete [type: final]
"""
    m = parse(dsl)
    assert len(m.root_states["main"].on_done) == 1
    assert m.root_states["main"].on_done[0].target == "complete"

    config = to_xstate(m)
    assert "onDone" in config["config"]["states"]["main"]
    print("  ✓ done.state")


if __name__ == "__main__":
    print("\nRunning XState DSL converter tests...\n")
    test_basic_machine()
    test_guards()
    test_compound_guards()
    test_actions()
    test_invoke()
    test_always()
    test_after()
    test_nested_states()
    test_parallel()
    test_history()
    test_guarded_branches()
    test_reenter()
    test_tags_and_meta()
    test_wildcard()
    test_xstate_to_dsl()
    test_xstate_complex_to_dsl()
    test_full_orderflow()
    test_done_state()
    print("\n✅ All tests passed!\n")
