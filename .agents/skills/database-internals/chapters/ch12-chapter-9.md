# Chapter 9: Failure Detection

## Core Idea
Failure detection is essential in distributed systems as it enables processes to detect failures or unresponsiveness promptly, ensuring system availability and liveness.

## Frameworks Introduced
- **Heartbeat Algorithm**: Uses periodic messaging to detect process failures.  
  - When to use: Asynchronous distributed systems where failure detection must be performed without timing assumptions.
  - How: Processes send heartbeat messages, increment counters for neighbors, and stop propagating upon detecting unresponsive peers.

- **φ-Accural Failure Detector**: Monitors heartbeats through pings or request-response sampling.  
  - When to use: Systems requiring continuous health monitoring with probabilistic accuracy.
  - How: Collects heartbeat arrival times to compute a failure probability threshold (φ).

- **Gossip-Based Failure Detection**: Uses information dissemination through random neighbors for reliable state propagation.  
  - When to use: Systems where robustness against network partitions is crucial.
  - How: Nodes periodically share and update heartbeat counters, ensuring aggregated health information across the cluster.

- **FUSE Failure Propagation Service**: Converts individual node failures into group failures using absence-based propagation.  
  - When to use: Systems requiring guaranteed failure detection even in partitioned networks.
  - How: Failsafe processes propagate unresponsiveness as group failures and stop responding upon detecting a failure.

## Key Concepts
- **Failure Detector**: A subsystem enabling processes to detect failures or unresponsiveness, crucial for liveness and safety.
- **Liveness**: The property that ensures tasks are completed successfully in a system.
- **Safety**: Ensures no incorrect decisions are made due to process failures.
- **Heartbeat**: Periodic messages sent between processes to maintain state and detect failures.
- **Ping**: A method to check if a process is still alive by expecting a response within a specified time period.

## Mental Models
- Use failure detectors when solving consensus problems in asynchronous systems.  
  - Think of failure detectors as abstractions that allow distributed systems to handle failures gracefully, trading off accuracy for completeness.
- Avoid assuming all processes are reachable or not failed without proper detection.  
  - Think of this as a critical step in designing robust distributed systems.

## Anti-patterns
- **Assuming all processes are reachable**: Failsafe mechanisms like heartbeats and pings help detect unresponsive peers, avoiding false positives.
- **Not implementing timeouts**: Can lead to infinite loops or delayed failure detection, missing failures that could propagate errors.  
  - Think of timeouts as essential for balancing accuracy and completeness in failure detection.

## Code Examples
```python
# Example code snippet demonstrating a simple heartbeat algorithm

class HeartbeatDetector:
    def __init__(self):
        self.heartbeats = {}  # Maps process IDs to their heartbeat counters
        self.last_response_time = {}

    def send_heartbeat(self, process_id):
        if process_id not in self.heartbeats or time.time() - self.heartbeats[process_id] > 5:
            self.heartbeats[process_id] = time.time()
            for neighbor in processes[process_id]:
                if neighbor not in self.last_response_time or time.time() - self.last_response_time[neighbor] > 5:
                    self.last_response_time[neighbor] = time.time()
                    self.HeartbeatDetector.send_heartbeat(neighbor)

    def detect_failure(self, process_id):
        current_time = time.time()
        for neighbor in processes[process_id]:
            if neighbor not in self.heartbeats or (current_time - self.heartbeats[neighbor]) > 5:
                return True
        return False
```

- **What it demonstrates**: A simple implementation of a heartbeat-based failure detection algorithm, demonstrating how processes can detect failures by monitoring peer heartbeats.

## Reference Tables

| Algorithm                  | Approach          | Pros                              | Cons                              |
|----------------------------|-------------------|------------------------------------|------------------------------------|
| Heartbeat Algorithm         | Periodic messaging | Simple to implement               | Susceptible to false positives    |
| φ-Accural Failure Detector  | Sampling and stats| Probabilistic accuracy           | Requires careful threshold tuning |
| Gossip-Based Detection      | Information spread | Robust against network partitions | Higher message overhead            |
| FUSE Failure Propagation   | Absence-based     | Reliable in partitioned networks  | May propagate failures prematurely |

## Key Takeaways
1. Use failure detectors to enable processes to detect failures or unresponsiveness promptly.
2. Understand the trade-offs between accuracy and completeness when implementing failure detection algorithms.
3. Choose appropriate algorithms based on system constraints, such as network partitions and response time requirements.

## Connects To
- Relates to FLP Impossibility (Chapter 9) in understanding distributed consensus limitations.
- Connects to distributed systems architecture for designing robust systems with failure handling mechanisms.