# Order Flow

```mermaid
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
```
