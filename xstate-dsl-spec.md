# XState v5 Compact DSL — Full Specification

> Compact text format that preserves 100% of XState v5 semantics.
> Designed for LLM context efficiency and human readability.

## 1. File Structure

```
machine: <id>
version: <semver>                          # optional
context: { key: type = default, ... }      # initial context
input: { key: type, ... }                  # actor input schema
output: { key: type, ... }                 # actor output schema (final state data)
types: { events: Event1 | Event2, ... }    # type hints (optional)

# --- states follow ---

state <name> [modifiers]
  <directives>
  <transitions>
```

## 2. State Declaration

```
state <name> [modifier...] [decorator...]
```

### Modifiers (in square brackets, space-separated)

| Modifier | XState equivalent |
|----------|------------------|
| `type: parallel` | `type: 'parallel'` |
| `type: final` | `type: 'final'` |
| `type: history` | `type: 'history'` |
| `type: history.deep` | `type: 'history'`, `history: 'deep'` |
| `initial: <child>` | `initial: '<child>'` |
| `tags: t1, t2` | `tags: ['t1', 't2']` |
| `meta: { key: val }` | `meta: { key: val }` |
| `description: "text"` | `description: 'text'` |
| `id: customId` | `id: 'customId'` |

### Decorators (entry/exit actions)

```
state loading [type: parallel]
  entry: startSpinner, logEnter
  exit: stopSpinner
```

## 3. Transitions

One line per transition. General syntax:

```
EVENT [guard1, guard2] / action1, action2 -> target
```

All parts are optional except at least one of EVENT or target:

```
# Full form
FETCH [isAuthed, hasToken] / setLoading, trackEvent -> loading

# No guard
FETCH / setLoading -> loading

# No action
FETCH [isAuthed] -> loading

# No target (self-transition, no re-entry)
CLICK / incrementCount

# Self-transition with re-entry
CLICK / incrementCount ->@ self          # reenter: true

# Multiple targets (parallel regions)
SYNC -> region1.idle & region2.ready
```

### Target Modifiers

| Syntax | Meaning |
|--------|---------|
| `-> target` | External transition to target |
| `->@ target` | Transition with `reenter: true` |
| `-> #customId` | Target by ID (cross-tree) |
| `-> .child` | Target child state (relative) |
| `-> ..sibling` | Target sibling (sugar) |

### Guarded Transition Chains

When the same event has multiple guarded branches:

```
SUBMIT
  [isValid, hasPermission] / save -> success
  [isValid] / queueForReview -> pending
  [else] / showErrors -> form
```

The `[else]` guard maps to no guard (fallback).

### Wildcard Event

```
* / logUnhandled -> error                  # matches any event
```

## 4. Special Transitions

### always (Eventless)

```
always [isDone] / cleanup -> complete
always [hasError] -> error
```

Maps to `always: [{ guard, actions, target }]`.

### after (Delayed)

```
after: 3000 -> timeout
after: 3000 [!isRetrying] / logTimeout -> timeout
after: getDelay -> timeout                 # dynamic delay (reference)
```

### done (Invoke/Child completion)

```
done / assignResult -> success             # onDone of invoke
done [isValid] / transform -> validated
done [else] -> error
```

### error (Invoke/Child error)

```
error / assignError -> failure             # onError of invoke
error [isRetryable] / retry -> loading
```

### done.state (Final child reached)

```
done.state / notifyParent -> next          # when a child final state is reached
```

## 5. Invoke

```
state loading
  invoke: fetchOrders [id: fetcher, input: { userId: context.userId }]
    done / assignData -> success
    error / assignError -> failure

  invoke: pollingActor [src: pollingMachine, id: poller]
    done -> idle

  invoke: callbackService [src: onAuthChange]
```

Multiple invocations per state are allowed (multiple `invoke:` lines).

### Invoke Modifiers

| Modifier | Meaning |
|----------|---------|
| `id: <name>` | `id` field |
| `src: <name>` | `src` reference (if different from inline name) |
| `input: { expr }` | `input` mapping |
| `systemId: <name>` | Register in actor system |

## 6. Actions — Full Syntax

### Inline short form (on transitions/entry/exit)

```
/ actionName                               # named action reference
/ assign({ count: inc })                   # inline assign
/ raise(EVENT_NAME)                        # raise event to self
/ sendTo(actorRef, { type: "PING" })       # send to another actor
/ emit({ type: "notify", data: x })        # emit to subscribers
/ log("message")                           # log action
/ stop(actorRef)                           # stop child actor
/ enqueueActions(fn)                       # dynamic actions
```

### Assign Shorthand

```
/ assign({ 
    count: ({ context }) => context.count + 1,
    items: ({ context, event }) => [...context.items, event.data],
    error: null
  })
```

Or by reference:

```
/ assign(addItem)                          # references implementation
```

### Action Params

```
/ sendNotification(level: "warn", target: "admin")
```

Maps to `{ type: 'sendNotification', params: { level: 'warn', target: 'admin' } }`.

## 7. Guards — Full Syntax

### Inline

```
[guardName]                                # simple reference
[!guardName]                               # not()
[guard1, guard2]                           # and([guard1, guard2])
[guard1 | guard2]                          # or([guard1, guard2])
[!guard1 | guard2, guard3]                 # or(not(guard1), and(guard2, guard3))
```

### Guard Params

```
[hasRole(role: "admin")]                   # guard with params
[minCount(min: 5)]
```

## 8. Context / Assign Expressions

Context is declared at the top level:

```
context: {
  items: Item[] = [],
  count: number = 0,
  user: User | null = null,
  error: string | null = null
}
```

Or as a function of input:

```
context: ({ input }) => ({
  userId: input.userId,
  items: [],
  retries: 0
})
```

## 9. Actors / Spawn

### In actions

```
/ spawn(childMachine, { id: "child-1", input: { x: 1 }, systemId: "myChild" })
```

### Actor types

```
invoke: promiseFn                          # Promise actor
invoke: callbackFn                         # Callback actor  
invoke: observableFn                       # Observable actor
invoke: childMachine                       # Machine actor
invoke: transitionFn                       # Transition actor
```

## 10. Parallel States

```
state dashboard [type: parallel]
  
  region notifications [initial: idle]
    state idle
      NEW_NOTIF / addNotif -> showing
    state showing
      after: 3000 -> idle

  region dataFeed [initial: polling]
    state polling
      invoke: pollData
        done / updateFeed ->@ polling
        error -> paused
    state paused
      RESUME -> polling
```

`region` is syntactic sugar for a child state within a parallel parent. Equivalent to nested `state` but clarifies intent.

## 11. Nested / Hierarchical States

Indentation defines hierarchy:

```
state active [initial: idle]

  state idle
    START -> running

  state running [initial: fetching]
    CANCEL -> idle

    state fetching
      invoke: fetchData
        done -> processing
        error -> ..idle              # go to parent's sibling

    state processing
      always [isComplete] -> #done   # go to ID
      always -> ..fetching           # retry
  
  state done [type: final]
```

## 12. History States

```
state editor [initial: draft]
  
  state draft
    PUBLISH -> published
    
  state published
    UNPUBLISH -> hist
  
  state hist [type: history.deep]            # deep history
    target: draft                            # default if no history
```

Shallow history:

```
state hist [type: history]                   # shallow (default)
  target: draft
```

## 13. Inter-Actor Communication

### sendTo

```
/ sendTo("actorId", { type: "UPDATE", data: context.value })
/ sendTo(context.parentRef, { type: "CHILD_DONE" })
/ sendTo(({ system }) => system.get("logger"), { type: "LOG" })
```

### sendParent (sugar)

```
/ sendParent({ type: "RESULT", data: context.output })
```

### emit

```
/ emit({ type: "stateChanged", state: "active" })
```

### forwardTo

```
/ forwardTo("childId")                     # forward current event
```

## 14. System Registration

```
state main
  invoke: authMachine [id: auth, systemId: globalAuth]
```

Any actor can reference via `({ system }) => system.get('globalAuth')`.

## 15. Complete Example

```
machine: orderFlow
version: 1.0.0
context: {
  items: OrderItem[] = [],
  total: number = 0,
  error: string | null = null,
  retries: number = 0,
  orderId: string | null = null
}
input: { userId: string, cartId: string }
output: { orderId: string, status: string }

state idle [initial] [tags: ready] [description: "Waiting for order submission"]
  entry: resetForm
  exit: clearErrors
  SUBMIT [hasItems, isAuthed] / validateCart -> validating
  SUBMIT [else] / showErrors
  LOAD_DRAFT / assignDraft -> editing

state editing
  UPDATE_ITEM / assignItem
  REMOVE_ITEM / removeItem, recalcTotal
  SUBMIT [hasItems] -> validating
  CANCEL / clearDraft -> idle

state validating
  invoke: validateOrder [input: { items: context.items, userId: input.userId }]
    done [isValid] / assignValidated -> confirming
    done [else] / assignErrors -> editing
    error / assignError -> editing
  after: 10000 -> editing

state confirming
  entry: sendTo(analytics, { type: "CHECKOUT_STARTED" })
  CONFIRM / setProcessing -> processing
  BACK -> editing
  CANCEL -> idle

state processing [type: parallel]
  entry: log("Processing order")

  region payment [initial: charging]
    state charging
      invoke: processPayment [id: paymentService]
        done / assignPaymentResult -> charged
        error [isRetryable] / incrementRetry -> retrying
        error [else] / assignError -> #paymentFailed
    state retrying
      after: getBackoffDelay [retries < 3] -> charging
      always [retries >= 3] -> #paymentFailed
    state charged [type: final]

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
  invoke: createShipment [input: { orderId: context.orderId }]
    done / assignTracking -> complete
    error / assignError -> supportNeeded

state complete [type: final]
  entry: sendParent({ type: "ORDER_COMPLETE", orderId: context.orderId })
  entry: emit({ type: "orderCompleted", data: context })
  output: { orderId: context.orderId, status: "complete" }

state paymentFailed [id: paymentFailed]
  entry: notifyUser, sendTo(support, { type: "PAYMENT_FAILED" })
  RETRY / resetRetries -> processing
  CANCEL / refundPartial -> cancelled

state supportNeeded
  entry: createTicket
  RESOLVED / assignResolution -> fulfilling
  CANCEL -> cancelled

state cancelled [type: final]
  entry: rollbackAll, emit({ type: "orderCancelled" })
  output: { orderId: context.orderId, status: "cancelled" }

# Wildcard — global error handling
* [isSystemError] / logSystemError, sendTo(monitoring, { type: "ERROR" }) -> supportNeeded
```

## 16. Syntax Reference Card

```
# Structure
machine: <id>
context: { ... }
input: { ... }
output: { ... }
state <name> [modifiers]

# Modifiers
[type: parallel | final | history | history.deep]
[initial: <child>] [initial]
[tags: a, b] [id: x] [description: "..."] [meta: {...}]

# Lifecycle
entry: action1, action2
exit: action1

# Transitions
EVENT [guards] / actions -> target
always [guard] / action -> target
after: <ms|ref> [guard] / action -> target
done [guard] / action -> target
error [guard] / action -> target
done.state -> target
* / action -> target

# Targets
-> stateName                  # standard
->@ stateName                 # reenter
-> #stateId                   # by ID
-> .child                     # child
-> ..sibling                  # sibling
-> region1.a & region2.b      # parallel targets

# Guards
[name]                        # simple
[!name]                       # not
[a, b]                        # and
[a | b]                       # or
[name(param: val)]            # with params
[else]                        # fallback

# Actions
/ name                        # reference
/ assign({...})               # inline assign
/ raise(EVENT)                # raise
/ sendTo(ref, {...})          # send
/ sendParent({...})           # send to parent
/ emit({...})                 # emit
/ spawn(machine, {...})       # spawn
/ stop(ref)                   # stop actor
/ log("msg")                  # log
/ forwardTo(ref)              # forward event
/ name(param: val)            # with params

# Invoke
invoke: <src|fn> [id: x, input: {...}, systemId: x]
  done / action -> target
  error / action -> target

# Hierarchy
state parent [initial: child]
  state child                 # indented = nested
  region name [initial: x]    # parallel region (sugar)

# History
state h [type: history.deep]
  target: defaultState        # fallback target

# Comments
# this is a comment
```

## 17. Parsing Notes for LLM

When converting this DSL back to XState `createMachine(config)`:

1. **Indentation** defines parent-child relationships (2-space or consistent indent).
2. **`region`** is just `state` inside a `type: 'parallel'` parent — sugar for readability.
3. **Guard combinators**: `[a, b]` → `and([a, b])`, `[a | b]` → `or([a, b])`, `[!a]` → `not(a)`.
4. **`[else]`** → transition with no guard (always last in the array).
5. **`->@`** → `{ reenter: true }` on the transition.
6. **`-> #id`** → string target `'#id'`.
7. **`done` / `error`** under `invoke:` → `onDone` / `onError` on that invocation.
8. **`done.state`** on a parallel parent → `onDone` of the compound state.
9. **Multiple `entry:` lines** → concatenated into single array.
10. **`output:`** on final state → `output` property.
11. **`[initial]`** modifier (without value) marks this state as the initial child.
12. **`context:` with `({ input }) =>`** → function form context.
13. **All action/guard references** map to `setup({ actions: {...}, guards: {...} })` in XState v5.

## 18. Compression Ratio

Typical compression vs XState v5 TypeScript config:

| Feature | XState TS | DSL | Ratio |
|---------|-----------|-----|-------|
| Simple 3-state machine | ~40 lines | ~10 lines | 4x |
| Parallel + invoke | ~120 lines | ~35 lines | 3.4x |
| Full order flow (above) | ~300 lines | ~80 lines | 3.7x |
| Setup + types boilerplate | ~50 lines | 2 lines | 25x |

**Average: ~4x compression** with zero semantic loss.
