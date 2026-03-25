"""Tests for bidirectional Mermaid ↔ XState v5 converter."""
import json
import pytest
from xstate_dsl import parse, to_xstate, to_mermaid


# ── Basic parsing ───────────────────────────────────────────────

class TestBasicParsing:
    def test_basic_machine(self):
        """Parse a simple 3-state machine."""
        mermaid = """
stateDiagram-v2
    %% machine: trafficLight
    %% context: { color: "red" }

    [*] --> red
    red --> green : TIMER
    green --> yellow : TIMER
    yellow --> red : TIMER
"""
        m = parse(mermaid)
        assert m.id == "trafficLight"
        assert set(m.root_states.keys()) == {"red", "green", "yellow"}
        assert m.initial == "red"

        t = m.root_states["red"].transitions[0]
        assert t.event == "TIMER"
        assert t.target == "green"

        config = to_xstate(m)
        assert config["config"]["id"] == "trafficLight"
        assert config["config"]["states"]["red"]["on"]["TIMER"] == "green"

    def test_minimal_machine(self):
        """Minimal valid machine — just header and one transition."""
        mermaid = """
stateDiagram-v2
    [*] --> only
"""
        m = parse(mermaid)
        assert m.initial == "only"
        assert "only" in m.root_states
        config = to_xstate(m)
        assert config["config"]["initial"] == "only"

    def test_machine_metadata(self):
        """Parse machine-level metadata: id, version, context, input."""
        mermaid = """
stateDiagram-v2
    %% machine: myApp
    %% version: 2.1.0
    %% context: { count: 0, name: "test" }
    %% input: { userId: string }

    [*] --> idle
"""
        m = parse(mermaid)
        assert m.id == "myApp"
        assert m.version == "2.1.0"
        assert "count: 0" in m.context
        assert "userId: string" in m.input

    def test_multiline_context(self):
        """Parse multiline context spanning multiple %% lines."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    %% context: {
    %%   items: [],
    %%   total: 0,
    %%   error: null
    %% }

    [*] --> idle
"""
        m = parse(mermaid)
        assert "items: []" in m.context
        assert "total: 0" in m.context
        assert "error: null" in m.context

    def test_no_explicit_initial(self):
        """Without [*] --> X, first state in dict becomes initial."""
        mermaid = """
stateDiagram-v2
    %% machine: test

    a --> b : GO
    b --> a : BACK
"""
        m = parse(mermaid)
        assert m.initial == "a"


# ── Guards ──────────────────────────────────────────────────────

class TestGuards:
    def test_simple_guard(self):
        mermaid = """
stateDiagram-v2
    %% machine: auth
    [*] --> idle
    idle --> checking : LOGIN [hasCredentials] / validate
    idle --> idle : LOGIN [else] / showError
"""
        m = parse(mermaid)
        t0 = m.root_states["idle"].transitions[0]
        assert t0.guards.guard.name == "hasCredentials"
        assert t0.target == "checking"

        t1 = m.root_states["idle"].transitions[1]
        assert t1.guards is None  # [else] → None

    def test_and_guard(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : EV [a, b]
"""
        m = parse(mermaid)
        t = m.root_states["s1"].transitions[0]
        assert t.guards.op == "and"
        assert len(t.guards.children) == 2

    def test_or_guard(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : EV [x | y]
"""
        m = parse(mermaid)
        t = m.root_states["s1"].transitions[0]
        assert t.guards.op == "or"

    def test_not_guard(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : EV [!z]
"""
        m = parse(mermaid)
        t = m.root_states["s1"].transitions[0]
        assert t.guards.guard.negated

    def test_parameterized_guard(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : CHECK [isGreaterThan(min: 5)]
"""
        m = parse(mermaid)
        t = m.root_states["s1"].transitions[0]
        assert t.guards.guard.name == "isGreaterThan"
        assert t.guards.guard.params == {"min": "5"}

        config = to_xstate(m)
        guard = config["config"]["states"]["s1"]["on"]["CHECK"]["guard"]
        assert guard["type"] == "isGreaterThan"
        assert guard["params"]["min"] == "5"

    def test_complex_guard_expression(self):
        """Guards: [a, b] AND combined with [else] fallback."""
        mermaid = """
stateDiagram-v2
    %% machine: form
    [*] --> editing
    editing --> success : SUBMIT [isValid, hasPermission] / save
    editing --> pending : SUBMIT [isValid] / queueReview
    editing --> editing : SUBMIT [else] / showErrors
"""
        m = parse(mermaid)
        s = m.root_states["editing"]
        assert len(s.transitions) == 3
        assert s.transitions[0].guards.op == "and"
        assert s.transitions[1].guards.guard.name == "isValid"
        assert s.transitions[2].guards is None

    def test_guard_to_xstate_not(self):
        """NOT guard produces correct XState config."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : EV [!blocked]
"""
        m = parse(mermaid)
        config = to_xstate(m)
        guard = config["config"]["states"]["s1"]["on"]["EV"]["guard"]
        assert guard == {"type": "not", "guard": "blocked"}

    def test_guard_to_xstate_and(self):
        """AND guard produces correct XState config."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : EV [a, b, c]
"""
        m = parse(mermaid)
        config = to_xstate(m)
        guard = config["config"]["states"]["s1"]["on"]["EV"]["guard"]
        assert guard["type"] == "and"
        assert len(guard["guards"]) == 3

    def test_guard_to_xstate_or(self):
        """OR guard produces correct XState config."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : EV [x | y]
"""
        m = parse(mermaid)
        config = to_xstate(m)
        guard = config["config"]["states"]["s1"]["on"]["EV"]["guard"]
        assert guard["type"] == "or"
        assert len(guard["guards"]) == 2


# ── Actions ─────────────────────────────────────────────────────

class TestActions:
    def test_inline_assign(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : CLICK / assign({ count: inc })
"""
        m = parse(mermaid)
        t = m.root_states["s1"].transitions[0]
        assert t.actions[0].kind == "assign"

    def test_sendTo_action(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s1 : SEND / sendTo(parent, { type: "DONE" })
"""
        m = parse(mermaid)
        t = m.root_states["s1"].transitions[0]
        assert t.actions[0].kind == "sendTo"

    def test_entry_exit_actions(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    state s1 {
        %% entry: startSpinner, logEnter
        %% exit: stopSpinner
    }
"""
        m = parse(mermaid)
        s = m.root_states["s1"]
        assert len(s.entry) == 2
        assert s.entry[0].name == "startSpinner"
        assert s.entry[1].name == "logEnter"
        assert len(s.exit) == 1
        assert s.exit[0].name == "stopSpinner"

    def test_multiple_transition_actions(self):
        """Multiple comma-separated actions on a transition."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : GO / doA, doB, doC
"""
        m = parse(mermaid)
        t = m.root_states["s1"].transitions[0]
        assert len(t.actions) == 3
        assert [a.name for a in t.actions] == ["doA", "doB", "doC"]

        config = to_xstate(m)
        actions = config["config"]["states"]["s1"]["on"]["GO"]["actions"]
        assert actions == ["doA", "doB", "doC"]

    def test_raise_action(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s1 : TICK / raise(TOCK)
"""
        m = parse(mermaid)
        t = m.root_states["s1"].transitions[0]
        assert t.actions[0].kind == "raise"
        assert t.actions[0].args == "TOCK"

    def test_emit_action(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : GO / emit({ type: "notify" })
"""
        m = parse(mermaid)
        t = m.root_states["s1"].transitions[0]
        assert t.actions[0].kind == "emit"

    def test_log_action(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : GO / log("entering s2")
"""
        m = parse(mermaid)
        t = m.root_states["s1"].transitions[0]
        assert t.actions[0].kind == "log"

    def test_spawn_action(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : GO / spawn(childMachine, { id: "child1" })
"""
        m = parse(mermaid)
        t = m.root_states["s1"].transitions[0]
        assert t.actions[0].kind == "spawn"

    def test_stop_action(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : GO / stop(childRef)
"""
        m = parse(mermaid)
        t = m.root_states["s1"].transitions[0]
        assert t.actions[0].kind == "stop"

    def test_sendParent_action(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : DONE / sendParent({ type: "CHILD_DONE" })
"""
        m = parse(mermaid)
        t = m.root_states["s1"].transitions[0]
        assert t.actions[0].kind == "sendParent"

    def test_forwardTo_action(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s1 : MSG / forwardTo(worker)
"""
        m = parse(mermaid)
        t = m.root_states["s1"].transitions[0]
        assert t.actions[0].kind == "forwardTo"


# ── Invocations ─────────────────────────────────────────────────

class TestInvocations:
    def test_invoke_with_done_error(self):
        mermaid = """
stateDiagram-v2
    %% machine: loader
    [*] --> loading
    loading --> success : done / assignResult
    loading --> failure : error / assignError

    state loading {
        %% invoke: fetchData [id: fetcher, input: { url: context.url }]
    }

    state success {
        %% type: final
    }
"""
        m = parse(mermaid)
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

    def test_invoke_without_modifiers(self):
        """Simple invoke: just service name, no id/input."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> loading
    loading --> done : done

    state loading {
        %% invoke: fetchSomething
    }

    state done {
        %% type: final
    }
"""
        m = parse(mermaid)
        inv = m.root_states["loading"].invocations[0]
        assert inv.src == "fetchSomething"
        assert inv.id is None
        assert inv.input is None

    def test_multiple_invocations(self):
        """Multiple invoke directives on a single state."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> loading

    state loading {
        %% invoke: fetchUser [id: userFetcher]
        %% invoke: fetchPosts [id: postsFetcher]
    }
"""
        m = parse(mermaid)
        s = m.root_states["loading"]
        assert len(s.invocations) == 2
        assert s.invocations[0].src == "fetchUser"
        assert s.invocations[0].id == "userFetcher"
        assert s.invocations[1].src == "fetchPosts"
        assert s.invocations[1].id == "postsFetcher"

    def test_invoke_with_systemId(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> active

    state active {
        %% invoke: workerMachine [id: worker, systemId: mainWorker]
    }
"""
        m = parse(mermaid)
        inv = m.root_states["active"].invocations[0]
        assert inv.system_id == "mainWorker"

        config = to_xstate(m)
        assert config["config"]["states"]["active"]["invoke"]["systemId"] == "mainWorker"

    def test_invoke_done_error_guards(self):
        """Invoke done/error with guards — multiple branches."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> loading
    loading --> success : done [isValid] / handle
    loading --> retry : error [isRetryable] / incrementRetry
    loading --> failed : error [else] / assignError

    state loading {
        %% invoke: fetchData [id: fetcher]
    }
"""
        m = parse(mermaid)
        inv = m.root_states["loading"].invocations[0]
        assert len(inv.on_done) == 1
        assert len(inv.on_error) == 2
        assert inv.on_error[0].guards.guard.name == "isRetryable"
        assert inv.on_error[1].guards is None  # [else]


# ── Transition types ────────────────────────────────────────────

class TestTransitionTypes:
    def test_always(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> checking
    checking --> valid : always [isValid] / process
    checking --> invalid : always [else]

    state valid {
        %% type: final
    }
"""
        m = parse(mermaid)
        s = m.root_states["checking"]
        assert len(s.always) == 2
        assert s.always[0].guards.guard.name == "isValid"
        assert s.always[0].target == "valid"
        assert s.always[1].guards is None

        config = to_xstate(m)
        always = config["config"]["states"]["checking"]["always"]
        assert len(always) == 2

    def test_after(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> waiting
    waiting --> timeout : after 3000
    waiting --> timeout : after 5000 [isImpatient] / warn
"""
        m = parse(mermaid)
        s = m.root_states["waiting"]
        assert len(s.after) == 2
        assert s.after[0].delay == 3000
        assert s.after[1].delay == 5000
        assert s.after[1].guards is not None

        config = to_xstate(m)
        after = config["config"]["states"]["waiting"]["after"]
        assert 3000 in after
        assert 5000 in after

    def test_after_named_delay(self):
        """Named delay (string, not integer)."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> waiting
    waiting --> timeout : after myDelay
"""
        m = parse(mermaid)
        assert m.root_states["waiting"].after[0].delay == "myDelay"

        config = to_xstate(m)
        assert "myDelay" in config["config"]["states"]["waiting"]["after"]

    def test_reenter(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s1 : REFRESH / reload @reenter
"""
        m = parse(mermaid)
        t = m.root_states["s1"].transitions[0]
        assert t.reenter
        assert t.target == "s1"

        config = to_xstate(m)
        t_cfg = config["config"]["states"]["s1"]["on"]["REFRESH"]
        assert t_cfg["reenter"] is True

    def test_self_loop_internal(self):
        """Self-loop without @reenter → internal transition (target=None in XState)."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s1 : TICK / increment
"""
        m = parse(mermaid)
        t = m.root_states["s1"].transitions[0]
        assert t.target is None  # internal
        assert t.reenter is False

        config = to_xstate(m)
        t_cfg = config["config"]["states"]["s1"]["on"]["TICK"]
        assert "target" not in t_cfg
        assert t_cfg["actions"] == "increment"

    def test_done_state(self):
        """done.state transitions for compound/parallel states."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> main
    main --> complete : done.state
    complete --> [*]

    state main {
        state a {
            [*] --> s1
            s1 --> s2 : GO
            s2 --> [*]
        }
        --
        state b {
            [*] --> s3
            s3 --> s4 : GO
            s4 --> [*]
        }
    }
"""
        m = parse(mermaid)
        assert len(m.root_states["main"].on_done) == 1
        assert m.root_states["main"].on_done[0].target == "complete"

        config = to_xstate(m)
        assert "onDone" in config["config"]["states"]["main"]

    def test_wildcard(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    %% on *: [isError] / logError -> s1

    [*] --> s1
    s1 --> s2 : GO
    s2 --> s1 : BACK
"""
        m = parse(mermaid)
        assert len(m.wildcard_transitions) == 1
        wt = m.wildcard_transitions[0]
        assert wt.event == "*"
        assert wt.guards.guard.name == "isError"

        config = to_xstate(m)
        assert "*" in config["config"]["on"]

    def test_transition_no_label(self):
        """Transition without a label — just source --> target."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2
"""
        m = parse(mermaid)
        t = m.root_states["s1"].transitions[0]
        assert t.target == "s2"
        assert t.event is None

    def test_multiple_events_same_source(self):
        """Multiple different events from the same state."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> idle
    idle --> loading : FETCH
    idle --> settings : OPEN_SETTINGS
    idle --> idle : REFRESH / reload
"""
        m = parse(mermaid)
        s = m.root_states["idle"]
        assert len(s.transitions) == 3

        config = to_xstate(m)
        on = config["config"]["states"]["idle"]["on"]
        assert "FETCH" in on
        assert "OPEN_SETTINGS" in on
        assert "REFRESH" in on


# ── State types ─────────────────────────────────────────────────

class TestStateTypes:
    def test_final_state(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> working
    working --> done : COMPLETE
    done --> [*]
"""
        m = parse(mermaid)
        assert m.root_states["done"].state_type == "final"

        config = to_xstate(m)
        assert config["config"]["states"]["done"]["type"] == "final"

    def test_final_with_entry_and_output(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> working
    working --> done : COMPLETE
    done --> [*]

    state done {
        %% type: final
        %% entry: notifyComplete
        %% output: { result: context.data }
    }
"""
        m = parse(mermaid)
        d = m.root_states["done"]
        assert d.state_type == "final"
        assert d.entry[0].name == "notifyComplete"
        assert d.output == "{ result: context.data }"

    def test_history_shallow(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> editor

    state editor {
        [*] --> draft
        draft --> published : PUBLISH
        published --> hist : UNPUBLISH

        state hist {
            %% type: history
            %% target: draft
        }
    }
"""
        m = parse(mermaid)
        hist = m.root_states["editor"].children["hist"]
        assert hist.state_type == "history"
        assert hist.history_type == "shallow"
        assert hist.history_target == "draft"

        config = to_xstate(m)
        hist_cfg = config["config"]["states"]["editor"]["states"]["hist"]
        assert hist_cfg["type"] == "history"
        assert hist_cfg["target"] == "draft"
        assert "history" not in hist_cfg  # shallow is default, not emitted

    def test_history_deep(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> editor

    state editor {
        [*] --> draft
        draft --> published : PUBLISH
        published --> hist : UNPUBLISH

        state hist {
            %% type: history.deep
            %% target: draft
        }
    }
"""
        m = parse(mermaid)
        hist = m.root_states["editor"].children["hist"]
        assert hist.state_type == "history"
        assert hist.history_type == "deep"

        config = to_xstate(m)
        hist_cfg = config["config"]["states"]["editor"]["states"]["hist"]
        assert hist_cfg["history"] == "deep"

    def test_tags_and_description(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> idle
    idle --> active : GO

    state idle {
        %% tags: ready, waiting
        %% description: "Initial state"
    }
"""
        m = parse(mermaid)
        s = m.root_states["idle"]
        assert s.tags == ["ready", "waiting"]
        assert s.description == "Initial state"

        config = to_xstate(m)
        s_cfg = config["config"]["states"]["idle"]
        assert s_cfg["tags"] == ["ready", "waiting"]
        assert s_cfg["description"] == "Initial state"

    def test_state_with_id(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> myState

    state myState {
        %% id: customId
    }
"""
        m = parse(mermaid)
        assert m.root_states["myState"].state_id == "customId"

        config = to_xstate(m)
        assert config["config"]["states"]["myState"]["id"] == "customId"

    def test_state_description_quoted(self):
        """state "Description" as name syntax."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> idle

    state "Waiting for input" as idle
"""
        m = parse(mermaid)
        assert m.root_states["idle"].description == "Waiting for input"


# ── Nested and parallel states ──────────────────────────────────

class TestHierarchy:
    def test_nested_states(self):
        mermaid = """
stateDiagram-v2
    %% machine: editor
    [*] --> active

    state active {
        [*] --> idle
        idle --> running : START
        running --> idle : CANCEL

        state running {
            [*] --> fetching
            fetching --> processing : LOADED
            processing --> idle : DONE
        }
    }

    state inactive {
    }
"""
        m = parse(mermaid)
        assert "active" in m.root_states
        assert "inactive" in m.root_states
        active = m.root_states["active"]
        assert active.initial == "idle"
        assert "idle" in active.children
        assert "running" in active.children
        running = active.children["running"]
        assert "fetching" in running.children

        config = to_xstate(m)
        active_cfg = config["config"]["states"]["active"]
        assert "idle" in active_cfg["states"]
        assert "running" in active_cfg["states"]

    def test_parallel(self):
        mermaid = """
stateDiagram-v2
    %% machine: dashboard
    [*] --> main

    state main {
        state notifications {
            [*] --> idle
            idle --> showing : NEW
            showing --> idle : after 3000
        }
        --
        state feed {
            [*] --> polling
            polling --> paused : PAUSE
            paused --> polling : RESUME
        }
    }
"""
        m = parse(mermaid)
        s = m.root_states["main"]
        assert s.state_type == "parallel"
        assert "notifications" in s.children
        assert "feed" in s.children
        assert "idle" in s.children["notifications"].children
        assert "polling" in s.children["feed"].children

        config = to_xstate(m)
        main_cfg = config["config"]["states"]["main"]
        assert main_cfg["type"] == "parallel"

    def test_three_parallel_regions(self):
        """Three parallel regions separated by --."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> main

    state main {
        state r1 {
            [*] --> a
        }
        --
        state r2 {
            [*] --> b
        }
        --
        state r3 {
            [*] --> c
        }
    }
"""
        m = parse(mermaid)
        s = m.root_states["main"]
        assert s.state_type == "parallel"
        assert len(s.children) == 3
        assert set(s.children.keys()) == {"r1", "r2", "r3"}

    def test_deeply_nested_3_levels(self):
        """3-level deep nesting."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> L1

    state L1 {
        [*] --> L2

        state L2 {
            [*] --> L3

            state L3 {
                [*] --> leaf
                leaf --> leaf : TICK
            }
        }
    }
"""
        m = parse(mermaid)
        l1 = m.root_states["L1"]
        l2 = l1.children["L2"]
        l3 = l2.children["L3"]
        assert "leaf" in l3.children

        config = to_xstate(m)
        leaf_cfg = config["config"]["states"]["L1"]["states"]["L2"]["states"]["L3"]["states"]["leaf"]
        assert "on" in leaf_cfg

    def test_cross_scope_transition(self):
        """In Mermaid, states are scoped to their block. A target inside a child
        scope creates a new child state, even if same name exists at root."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> active
    active --> done : FINISH

    state active {
        [*] --> working
        working --> done : SHORTCUT
    }

    state done {
        %% type: final
    }
"""
        m = parse(mermaid)
        assert "done" in m.root_states
        # 'done' also created inside active (Mermaid scoping)
        assert "done" in m.root_states["active"].children

    def test_cross_scope_ancestor_exists(self):
        """If target already exists in ancestor scope before child parsing, it's not recreated."""
        mermaid = """
stateDiagram-v2
    %% machine: test

    state done {
        %% type: final
    }

    [*] --> active
    active --> done : FINISH

    state active {
        [*] --> working
        working --> done : SHORTCUT
    }
"""
        m = parse(mermaid)
        assert "done" in m.root_states
        # Now 'done' was declared before 'active', so ancestor check works
        assert "done" not in m.root_states["active"].children

    def test_empty_state_block(self):
        """Empty state block should still parse."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : GO

    state s1 {
    }

    state s2 {
    }
"""
        m = parse(mermaid)
        assert "s1" in m.root_states
        assert "s2" in m.root_states


# ── XState → Mermaid (to_mermaid) ──────────────────────────────

class TestToMermaid:
    def test_simple_roundtrip(self):
        xstate_config = {
            "id": "toggle",
            "initial": "inactive",
            "states": {
                "inactive": {"on": {"TOGGLE": "active"}},
                "active": {
                    "on": {"TOGGLE": "inactive"},
                    "after": {5000: "inactive"},
                },
            },
        }

        mermaid_text = to_mermaid(xstate_config)
        assert "%% machine: toggle" in mermaid_text
        assert "inactive --> active : TOGGLE" in mermaid_text
        assert "active --> inactive : TOGGLE" in mermaid_text
        assert "active --> inactive : after 5000" in mermaid_text

        m = parse(mermaid_text)
        config = to_xstate(m)
        assert config["config"]["id"] == "toggle"

    def test_complex_roundtrip(self):
        xstate_config = {
            "id": "auth",
            "initial": "idle",
            "states": {
                "idle": {
                    "on": {
                        "LOGIN": {
                            "target": "authenticating",
                            "guard": "hasCredentials",
                            "actions": "setLoading",
                        }
                    }
                },
                "authenticating": {
                    "invoke": {
                        "src": "authService",
                        "id": "auth",
                        "onDone": {
                            "target": "authenticated",
                            "actions": "assignUser",
                        },
                        "onError": [
                            {
                                "target": "idle",
                                "guard": "isRetryable",
                                "actions": "incrementRetry",
                            },
                            {"target": "failed", "actions": "assignError"},
                        ],
                    },
                    "after": {10000: "idle"},
                },
                "authenticated": {"type": "final", "entry": "notifySuccess"},
                "failed": {"on": {"RETRY": "authenticating"}},
            },
        }

        mermaid_text = to_mermaid(xstate_config)
        assert "%% machine: auth" in mermaid_text
        assert "%% invoke: authService" in mermaid_text
        assert "after 10000" in mermaid_text
        assert "type: final" in mermaid_text

        m = parse(mermaid_text)
        assert m.id == "auth"
        assert len(m.root_states["authenticating"].invocations) == 1

    def test_to_mermaid_parallel(self):
        """to_mermaid emits parallel regions with -- separator."""
        xstate_config = {
            "id": "par",
            "initial": "main",
            "states": {
                "main": {
                    "type": "parallel",
                    "states": {
                        "r1": {
                            "initial": "a",
                            "states": {
                                "a": {"on": {"GO": "b"}},
                                "b": {},
                            },
                        },
                        "r2": {
                            "initial": "c",
                            "states": {
                                "c": {"on": {"GO": "d"}},
                                "d": {},
                            },
                        },
                    },
                }
            },
        }

        mermaid_text = to_mermaid(xstate_config)
        assert "state main {" in mermaid_text
        assert "--" in mermaid_text
        assert "state r1 {" in mermaid_text
        assert "state r2 {" in mermaid_text

    def test_to_mermaid_preserves_entry_exit(self):
        xstate_config = {
            "id": "test",
            "initial": "idle",
            "states": {
                "idle": {
                    "entry": "logEntry",
                    "exit": "logExit",
                    "on": {"GO": "active"},
                },
                "active": {},
            },
        }

        mermaid_text = to_mermaid(xstate_config)
        assert "%% entry: logEntry" in mermaid_text
        assert "%% exit: logExit" in mermaid_text

    def test_to_mermaid_history(self):
        xstate_config = {
            "id": "test",
            "initial": "editor",
            "states": {
                "editor": {
                    "initial": "draft",
                    "states": {
                        "draft": {"on": {"PUBLISH": "published"}},
                        "published": {},
                        "hist": {
                            "type": "history",
                            "history": "deep",
                            "target": "draft",
                        },
                    },
                }
            },
        }

        mermaid_text = to_mermaid(xstate_config)
        assert "%% type: history.deep" in mermaid_text
        assert "%% target: draft" in mermaid_text

    def test_to_mermaid_setup_config_pair(self):
        """to_mermaid handles {setup, config} pair."""
        wrapped = {
            "setup": {"actions": {}, "guards": {}},
            "config": {
                "id": "test",
                "initial": "idle",
                "states": {
                    "idle": {"on": {"GO": "active"}},
                    "active": {},
                },
            },
        }

        mermaid_text = to_mermaid(wrapped)
        assert "%% machine: test" in mermaid_text
        assert "idle --> active : GO" in mermaid_text


# ── Full round-trip tests ───────────────────────────────────────

class TestRoundTrip:
    """Mermaid → XState → Mermaid → parse → verify no semantic loss."""

    def _roundtrip(self, mermaid: str):
        """Parse, convert to XState, convert back to Mermaid, parse again."""
        m1 = parse(mermaid)
        config = to_xstate(m1)
        mermaid2 = to_mermaid(config)
        m2 = parse(mermaid2)
        return m1, config, m2

    def test_roundtrip_basic(self):
        mermaid = """
stateDiagram-v2
    %% machine: rt1
    [*] --> a
    a --> b : GO [isReady] / doStuff
    b --> a : BACK
"""
        m1, _, m2 = self._roundtrip(mermaid)
        assert m2.id == m1.id
        assert set(m2.root_states.keys()) == set(m1.root_states.keys())
        assert m2.root_states["a"].transitions[0].event == "GO"
        assert m2.root_states["a"].transitions[0].guards.guard.name == "isReady"

    def test_roundtrip_invoke(self):
        mermaid = """
stateDiagram-v2
    %% machine: rt2
    [*] --> loading
    loading --> success : done / handle
    loading --> failure : error

    state loading {
        %% invoke: fetchData [id: fetcher]
    }
"""
        m1, config, m2 = self._roundtrip(mermaid)
        assert len(m2.root_states["loading"].invocations) == 1
        assert m2.root_states["loading"].invocations[0].src == "fetchData"

    def test_roundtrip_nested(self):
        mermaid = """
stateDiagram-v2
    %% machine: rt3
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
"""
        _, _, m2 = self._roundtrip(mermaid)
        assert "outer" in m2.root_states
        assert "inner" in m2.root_states["outer"].children
        assert "working" in m2.root_states["outer"].children["inner"].children

    def test_roundtrip_parallel(self):
        mermaid = """
stateDiagram-v2
    %% machine: rt4
    [*] --> main

    state main {
        state upload {
            [*] --> idle
            idle --> uploading : START
            uploading --> idle : DONE
        }
        --
        state progress {
            [*] --> hidden
            hidden --> visible : SHOW
            visible --> hidden : HIDE
        }
    }
"""
        _, _, m2 = self._roundtrip(mermaid)
        assert m2.root_states["main"].state_type == "parallel"
        assert "upload" in m2.root_states["main"].children
        assert "progress" in m2.root_states["main"].children

    def test_roundtrip_after_always(self):
        mermaid = """
stateDiagram-v2
    %% machine: rt5
    [*] --> checking
    checking --> valid : always [isValid]
    checking --> invalid : always [else]
    checking --> timeout : after 5000
"""
        _, _, m2 = self._roundtrip(mermaid)
        s = m2.root_states["checking"]
        assert len(s.always) == 2
        assert len(s.after) == 1

    def test_roundtrip_full_orderflow(self):
        """Round-trip the full orderflow.md example."""
        mermaid = """
stateDiagram-v2
    %% machine: orderFlow
    %% version: 1.0.0
    %% context: {
    %%   items: [],
    %%   total: 0,
    %%   error: null,
    %%   retries: 0
    %% }
    %% input: { userId: string, cartId: string }

    [*] --> idle
    idle --> validating : SUBMIT [hasItems, isAuthed] / validateCart
    idle --> idle : SUBMIT [else] / showErrors

    validating --> confirming : done [isValid] / assignValidated
    validating --> editing : done [else] / assignErrors
    validating --> editing : error / assignError
    validating --> editing : after 10000

    editing --> editing : UPDATE_ITEM / assignItem
    editing --> editing : REMOVE_ITEM / removeItem, recalcTotal
    editing --> validating : SUBMIT [hasItems]
    editing --> idle : CANCEL / clearDraft

    confirming --> processing : CONFIRM / setProcessing
    confirming --> editing : BACK
    confirming --> idle : CANCEL

    processing --> fulfilling : done.state

    fulfilling --> complete : done / assignTracking
    fulfilling --> supportNeeded : error / assignError

    complete --> [*]

    supportNeeded --> fulfilling : RESOLVED
    supportNeeded --> cancelled : CANCEL

    cancelled --> [*]

    state idle {
        %% entry: resetForm
        %% exit: clearErrors
        %% tags: ready
        %% description: "Waiting for order"
    }

    state validating {
        %% invoke: validateOrder [id: validator, input: { items: context.items }]
    }

    state processing {
        state payment {
            [*] --> charging
            charging --> charged : done / assignPaymentResult
            charging --> retrying : error [isRetryable] / incrementRetry
            charging --> failed : error [else] / assignError
            retrying --> charging : after 2000
            retrying --> failed : always [retries >= 3]
            charged --> [*]

            state charging {
                %% invoke: processPayment [id: paymentSvc]
            }
        }
        --
        state inventory {
            [*] --> reserving
            reserving --> reserved : done / assignReservation
            reserving --> reserveFailed : error
            reserved --> [*]
            reserveFailed --> reserving : RETRY_RESERVE

            state reserving {
                %% invoke: reserveInventory
            }
        }
    }

    state fulfilling {
        %% invoke: createShipment
    }

    state complete {
        %% type: final
        %% entry: notifyComplete
    }

    state cancelled {
        %% type: final
        %% entry: rollbackAll
    }
"""
        m1, config, m2 = self._roundtrip(mermaid)
        assert m2.id == "orderFlow"
        assert len(m2.root_states) >= 8
        assert m2.root_states["processing"].state_type == "parallel"
        assert "payment" in m2.root_states["processing"].children
        assert "inventory" in m2.root_states["processing"].children


# ── XState JSON structure validation ────────────────────────────

class TestXStateStructure:
    """Validate the XState v5 JSON config structure is correct."""

    def test_setup_has_refs(self):
        """setup block collects all action/guard/actor references."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : GO [myGuard] / myAction

    state s1 {
        %% entry: onEnter
        %% invoke: myService [id: svc]
    }
"""
        config = to_xstate(parse(mermaid))
        setup = config["setup"]
        assert "myGuard" in setup["guards"]
        assert "myAction" in setup["actions"]
        assert "onEnter" in setup["actions"]
        assert "myService" in setup["actors"]

    def test_guarded_branches_array(self):
        """Multiple guarded transitions for same event → array in XState."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : EV [a] / doA
    s1 --> s3 : EV [b] / doB
    s1 --> s4 : EV [else] / doDefault
"""
        config = to_xstate(parse(mermaid))
        ev = config["config"]["states"]["s1"]["on"]["EV"]
        assert isinstance(ev, list)
        assert len(ev) == 3

    def test_single_transition_not_array(self):
        """Single transition for an event → not wrapped in array."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : GO
"""
        config = to_xstate(parse(mermaid))
        assert config["config"]["states"]["s1"]["on"]["GO"] == "s2"

    def test_invoke_structure(self):
        """Verify invoke config shape matches XState v5 spec."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> loading
    loading --> ok : done / handle
    loading --> err : error / handle

    state loading {
        %% invoke: fetchData [id: myFetcher, input: { url: context.url }]
    }
"""
        config = to_xstate(parse(mermaid))
        inv = config["config"]["states"]["loading"]["invoke"]
        assert inv["src"] == "fetchData"
        assert inv["id"] == "myFetcher"
        assert "onDone" in inv
        assert "onError" in inv
        # input should be a __raw__ expression
        assert inv["input"]["__raw__"]

    def test_after_structure(self):
        """after config is keyed by delay value."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : after 3000
    s1 --> s3 : after 5000 [cond] / act
"""
        config = to_xstate(parse(mermaid))
        after = config["config"]["states"]["s1"]["after"]
        assert after[3000] == "s2"
        assert isinstance(after[5000], dict)
        assert after[5000]["target"] == "s3"
        assert after[5000]["guard"] == "cond"

    def test_always_structure(self):
        """always is an array of transition objects."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : always [ready]
    s1 --> s3 : always [else]
"""
        config = to_xstate(parse(mermaid))
        always = config["config"]["states"]["s1"]["always"]
        assert isinstance(always, list)
        assert len(always) == 2
        assert always[0]["guard"] == "ready"
        assert always[0]["target"] == "s2"
        # [else] → no guard key
        assert "guard" not in always[1]

    def test_final_state_structure(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> done : FINISH
    done --> [*]

    state done {
        %% type: final
        %% entry: cleanup
    }
"""
        config = to_xstate(parse(mermaid))
        done = config["config"]["states"]["done"]
        assert done["type"] == "final"
        assert done["entry"] == "cleanup"

    def test_parallel_structure(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> par

    state par {
        state a {
            [*] --> a1
        }
        --
        state b {
            [*] --> b1
        }
    }
"""
        config = to_xstate(parse(mermaid))
        par = config["config"]["states"]["par"]
        assert par["type"] == "parallel"
        assert "a" in par["states"]
        assert "b" in par["states"]
        # parallel states should NOT have "initial" property
        assert "initial" not in par

    def test_history_structure(self):
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> main

    state main {
        [*] --> s1
        s1 --> s2 : GO
        s2 --> hist : BACK

        state hist {
            %% type: history.deep
            %% target: s1
        }
    }
"""
        config = to_xstate(parse(mermaid))
        hist = config["config"]["states"]["main"]["states"]["hist"]
        assert hist["type"] == "history"
        assert hist["history"] == "deep"
        assert hist["target"] == "s1"


# ── Edge cases ──────────────────────────────────────────────────

class TestEdgeCases:
    def test_state_declared_before_transition(self):
        """State block appears before its transition is declared."""
        mermaid = """
stateDiagram-v2
    %% machine: test

    state loading {
        %% invoke: fetchData
    }

    [*] --> loading
    loading --> done : done

    state done {
        %% type: final
    }
"""
        m = parse(mermaid)
        assert m.initial == "loading"
        assert len(m.root_states["loading"].invocations) == 1
        assert m.root_states["loading"].invocations[0].on_done[0].target == "done"

    def test_transition_before_state_block(self):
        """Transitions declared before the state block with invoke."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> loading
    loading --> success : done / handle
    loading --> failure : error / handle

    state loading {
        %% invoke: myService
    }
"""
        m = parse(mermaid)
        inv = m.root_states["loading"].invocations[0]
        assert len(inv.on_done) == 1
        assert len(inv.on_error) == 1

    def test_special_chars_in_guard(self):
        """Guard with comparison operators."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s2 : always [retries >= 3]
"""
        m = parse(mermaid)
        assert m.root_states["s1"].always[0].guards.guard.name == "retries >= 3"

    def test_whitespace_variations(self):
        """Different whitespace around arrows and labels."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*]-->s1
    s1-->s2:GO
    s2 -->  s3  :  NEXT [ready] / doIt
"""
        m = parse(mermaid)
        assert m.initial == "s1"
        assert m.root_states["s1"].transitions[0].target == "s2"
        assert m.root_states["s2"].transitions[0].guards.guard.name == "ready"

    def test_action_with_guard_no_target_change(self):
        """Self-transition with guard and action."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> s1
    s1 --> s1 : UPDATE [isValid] / save
"""
        m = parse(mermaid)
        t = m.root_states["s1"].transitions[0]
        assert t.target is None  # internal self-transition
        assert t.guards.guard.name == "isValid"
        assert t.actions[0].name == "save"

    def test_done_without_invoke_becomes_onDone(self):
        """'done' transition on a state without invoke → onDone (compound state done)."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    [*] --> compound
    compound --> next : done

    state compound {
        [*] --> inner
        inner --> final : GO
        final --> [*]
    }
"""
        m = parse(mermaid)
        # No invocations, so 'done' should go to on_done
        assert len(m.root_states["compound"].on_done) == 1


# ── JSON serialization ──────────────────────────────────────────

class TestJsonSerialization:
    def test_json_serializable(self):
        """Entire XState config is JSON-serializable."""
        mermaid = """
stateDiagram-v2
    %% machine: test
    %% context: { count: 0 }
    [*] --> idle
    idle --> loading : FETCH [isReady] / setLoading

    state loading {
        %% invoke: fetchData [id: fetcher, input: { url: context.url }]
    }
"""
        config = to_xstate(parse(mermaid))
        # Should not throw
        json_str = json.dumps(config, indent=2, default=str)
        parsed_back = json.loads(json_str)
        assert parsed_back["config"]["id"] == "test"

    def test_to_mermaid_output_is_valid_mermaid_header(self):
        """Output always starts with stateDiagram-v2."""
        config = {
            "id": "test",
            "initial": "idle",
            "states": {"idle": {"on": {"GO": "done"}}, "done": {}},
        }
        text = to_mermaid(config)
        assert text.strip().startswith("stateDiagram-v2")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
