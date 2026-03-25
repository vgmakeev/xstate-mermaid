# Order Flow

```mermaid
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
