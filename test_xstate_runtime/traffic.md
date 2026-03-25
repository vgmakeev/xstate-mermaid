```mermaid
stateDiagram-v2
    %% machine: trafficLight

    [*] --> red
    red --> green : TIMER
    green --> yellow : TIMER
    yellow --> red : TIMER
```
