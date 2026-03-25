# xstate-dsl — Bidirectional XState v5 DSL Converter

Compact text DSL for describing XState v5 machines with bidirectional conversion to JSON config. ~4x compression with zero semantic loss.

## Install

```bash
uv tool install ./xstate-mermaid
```

## Quick Start

```bash
# DSL -> XState v5 JSON
xstate-dsl dsl2xstate input.dsl

# XState v5 JSON -> DSL
xstate-dsl xstate2dsl machine.json

# Roundtrip (DSL -> JSON -> DSL, verify losslessness)
xstate-dsl roundtrip input.dsl

# Stdin / output file
cat file.dsl | xstate-dsl dsl2xstate -
xstate-dsl dsl2xstate input.dsl -o output.json

# Without installing (one-off)
uvx --from ./xstate-mermaid xstate-dsl dsl2xstate input.dsl
```

### Python API

```python
from xstate_dsl import parse, to_xstate, to_dsl

machine = parse(dsl_text)           # DSL -> AST
config  = to_xstate(machine)        # AST -> {setup, config}
dsl_out = to_dsl(xstate_config)     # JSON config -> DSL
```

## DSL Format

Full specification — [xstate-dsl-spec.md](xstate-dsl-spec.md).

### Minimal Example

```
machine: trafficLight
context: { color: "red" }

state red [initial]
  TIMER -> green

state green
  TIMER -> yellow

state yellow
  TIMER -> red
```

### Supported Features

```
# Machine header
machine: <id>
version: <semver>
context: { key: type = default, ... }
input: { key: type, ... }
output: { key: type, ... }

# States
state <name> [type: parallel | final | history | history.deep]
             [initial: <child>] [initial]
             [tags: a, b] [id: x] [description: "..."]

# Entry / exit
entry: action1, action2
exit: action1

# Transitions
EVENT [guards] / actions -> target
always [guard] / action -> target
after: <ms|ref> [guard] / action -> target
* / action -> target                           # wildcard

# Guards
[name]              # simple
[!name]             # not
[a, b]              # and
[a | b]             # or
[name(param: val)]  # with params
[else]              # fallback

# Actions
/ name                    # reference
/ assign({...})           # inline assign
/ raise(EVENT)            # raise
/ sendTo(ref, {...})      # send to actor
/ sendParent({...})       # send to parent
/ emit({...})             # emit to subscribers
/ spawn(machine, {...})   # spawn child actor
/ stop(ref)               # stop actor

# Invoke
invoke: <src> [id: x, input: {...}, systemId: x]
  done / action -> target
  error / action -> target

# Nested states (via indentation)
state parent [initial: child]
  state child

# Parallel regions
state dashboard [type: parallel]
  region notifications [initial: idle]
    state idle
    state showing
  region feed [initial: polling]
    state polling
    state paused

# Target modifiers
-> target           # standard
->@ target          # reenter: true
-> #stateId         # by ID (cross-tree)
-> .child           # child
-> ..sibling        # sibling
```

### Full Example

```
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
```

## Package Structure

```
xstate-mermaid/
  pyproject.toml         # xstate-dsl package
  xstate_dsl/
    __init__.py          # public API: parse, to_xstate, to_dsl
    __main__.py          # CLI entry point
    models.py            # AST: Machine, StateNode, Transition, ...
    parser.py            # DSL text -> Machine AST
    to_xstate.py         # Machine AST -> XState v5 JSON config
    to_dsl.py            # XState v5 JSON config -> DSL text
  test_converter.py      # 18 tests
  orderflow.dsl          # example — order flow
  xstate-dsl-spec.md     # full DSL specification
```

## Tests

```bash
python xstate-mermaid/test_converter.py
```

## Compression

| Scenario | XState TS | DSL | Ratio |
|----------|-----------|-----|-------|
| Simple machine (3 states) | ~40 lines | ~10 lines | 4x |
| Parallel + invoke | ~120 lines | ~35 lines | 3.4x |
| Full order flow | ~300 lines | ~80 lines | 3.7x |
| Setup + types boilerplate | ~50 lines | 2 lines | 25x |
