# xstate-dsl

> Mermaid-inspired compact text DSL for [XState v5](https://stately.ai/docs/xstate) state machines, designed for LLM agents. ~4x compression vs JSON/TS config with zero semantic loss.

## Why

XState v5 configs are verbose JSON/TypeScript — expensive in LLM context tokens and slow to generate. This DSL solves three problems:

1. **Faster generation** — an LLM agent outputs ~4x fewer tokens to describe the same state machine, which directly speeds up generation
2. **Cheaper to read** — `.md` files with `mermaid` code blocks in the repo are compact and unambiguous, so agents parse the full machine logic in a fraction of the context window
3. **State machine as spec** — an `.md` file can serve as a living specification for your SDLC: define workflows, hand them to agents for implementation, then roundtrip back to verify nothing was lost

The syntax is Mermaid-inspired — not fully compatible, but close enough to be largely renderable by Mermaid tools while carrying full XState v5 semantics.

```
machine: trafficLight

state red [initial]
  TIMER -> green

state green
  TIMER -> yellow

state yellow
  TIMER -> red
```

## Features

- **DSL -> XState v5 JSON** — write state machines in a concise, readable format
- **XState v5 JSON -> DSL** — convert existing machines to compact DSL
- **Roundtrip verification** — `DSL -> JSON -> DSL` to prove losslessness
- **Full XState v5 coverage** — parallel states, invocations, guards, actions, history, nested hierarchies
- **~4x compression** vs equivalent TypeScript/JSON config
- **Python API** — `parse()`, `to_xstate()`, `to_dsl()` for programmatic use

## Installation

```bash
# One-liner via uvx (no install needed)
uvx --from "git+https://github.com/vgmakeev/xstate-mermaid.git" xstate-dsl dsl2xstate machine.md

# Or install globally
uv tool install "git+https://github.com/vgmakeev/xstate-mermaid.git"
```

## Usage

### CLI

```bash
# DSL -> XState v5 JSON
xstate-dsl dsl2xstate machine.md

# XState v5 JSON -> DSL
xstate-dsl xstate2dsl machine.json

# Roundtrip verification
xstate-dsl roundtrip machine.md

# Pipe from stdin, write to file
cat machine.md | xstate-dsl dsl2xstate - -o output.json
```

### Python API

```python
from xstate_dsl import parse, to_xstate, to_dsl

machine = parse(dsl_text)           # DSL text -> AST
config  = to_xstate(machine)        # AST -> XState v5 config dict
dsl_out = to_dsl(xstate_config)     # XState v5 config -> DSL text
```

## DSL Syntax

Full specification: [xstate-dsl-spec.md](xstate-dsl-spec.md)

### Quick Reference

```
machine: <id>
version: <semver>
context: { key: type = default, ... }
input: { key: type, ... }
output: { key: type, ... }

state <name> [type: parallel|final|history|history.deep]
             [initial] [initial: <child>] [tags: a, b] [id: x]
  entry: action1, action2
  exit: action1

  # Transitions
  EVENT [guard] / action -> target
  always [guard] / action -> target
  after: 3000 [guard] / action -> target
  * / action -> target                     # wildcard

  # Invocations
  invoke: fetchData [id: fetcher, input: { ... }]
    done / assignResult -> success
    error / assignError -> failure
```

<details>
<summary><strong>Guards</strong></summary>

```
[name]                  # simple reference
[!name]                 # negation
[a, b]                  # AND
[a | b]                 # OR
[name(key: val)]        # parameterized
[else]                  # fallback (no guard)
```

</details>

<details>
<summary><strong>Actions</strong></summary>

```
/ name                  # reference
/ assign({...})         # inline assign
/ raise(EVENT)          # raise event
/ sendTo(ref, {...})    # send to actor
/ sendParent({...})     # send to parent
/ emit({...})           # emit to subscribers
/ spawn(machine, {...}) # spawn child actor
/ stop(ref)             # stop actor
/ log("msg")            # log
```

</details>

<details>
<summary><strong>Target modifiers</strong></summary>

```
-> target               # standard
->@ target              # reenter: true
-> #stateId             # by ID (cross-tree)
-> .child               # relative child
-> ..sibling            # relative sibling
-> region1.a & region2.b  # parallel targets
```

</details>

<details>
<summary><strong>Parallel states & regions</strong></summary>

```
state dashboard [type: parallel]

  region notifications [initial: idle]
    state idle
      NEW_NOTIF / addNotif -> showing
    state showing
      after: 3000 -> idle

  region feed [initial: polling]
    state polling
      invoke: pollData
        done / updateFeed ->@ polling
    state paused
      RESUME -> polling
```

</details>

### Example: Order Flow

See [`orderflow.md`](orderflow.md) for a complete example with parallel processing, invocations, guards, and error handling.

## Compression Ratio

| Scenario | XState TS | DSL | Ratio |
|----------|-----------|-----|-------|
| Simple machine (3 states) | ~40 lines | ~10 lines | **4x** |
| Parallel + invoke | ~120 lines | ~35 lines | **3.4x** |
| Full order flow | ~300 lines | ~80 lines | **3.7x** |
| Setup + types boilerplate | ~50 lines | 2 lines | **25x** |

## Tests

```bash
python test_converter.py
```

## Project Structure

```
xstate_dsl/
  __init__.py       # Public API: parse, to_xstate, to_dsl
  __main__.py       # CLI entry point
  models.py         # AST data classes
  parser.py         # DSL text -> AST
  to_xstate.py      # AST -> XState v5 JSON
  to_dsl.py         # XState v5 JSON -> DSL text
```

## License

MIT
