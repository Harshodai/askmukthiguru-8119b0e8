# Chapter 13: CHAPTER 10

## Core Idea
A single leader in a distributed system ensures efficient task coordination, avoids split brain issues, and minimizes communication overhead by centralizing responsibilities.

## Frameworks Introduced
- **Bully Algorithm**: 
  - When to use: Distributed systems requiring a stable leader due to high latency or unreliable networks.
  - How: Elects the highest-ranked process as the leader; uses hierarchy for notifications.
  
- **Ring Algorithm**:
  - When to use: Systems with predictable network partitions where a single leader can handle multiple tasks efficiently.
  - How: Processes form a ring, electing a leader by circulating messages around the ring.

## Key Concepts
- **Split Brain**: A system-wide issue caused by multiple leaders, leading to inconsistent states. Algorithms like Bully and Ring aim to mitigate this.
- **Election Algorithm**: A procedure for selecting a single process as the primary coordinator in a distributed system.

## Mental Models
- Use **Bully Algorithm** when you need a stable leader that can handle network partitions gracefully.
  - Think of it as ensuring "centralized control" over distributed tasks, especially in systems where reliability is critical.

## Anti-patterns
- **Multiple Leaders**: Avoid this by using algorithms like Bully or Ring to ensure only one leader exists at any time, preventing split brain issues.

## Code Examples
```python
def bully_election proposers, acceptors):
    if no leaders:
        elect the highest-ranked process as the leader.
    else:
        if a leader crashes:
            notify all other processes of the crash.
            elect the next highest-ranked available process as the new leader.
```

## Reference Tables

| Algorithm      | Use Case                          | Network Requirements          |
|----------------|------------------------------------|------------------------------|
| Bully Algorithm| High-latency networks               | No explicit network partitioning    |
| Ring Algorithm  | Networks with predictable partitions| Single or multiple leaders       |

## Key Takeaways
1. Use the **Bully Algorithm** for systems requiring a stable leader in high-latency environments.
2. Opt for the **Ring Algorithm** to handle networks with predictable partitions efficiently.
3. Always consider the trade-offs between complexity and reliability when choosing an election algorithm.

## Connects To
- Failsafe Design: Ensures systems remain functional despite component failures.
- Distributed Transactions: Maintains consistency by relying on a single leader for coordination.