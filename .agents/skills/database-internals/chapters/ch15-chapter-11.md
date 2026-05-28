# Chapter 15: Chapter 11

## Core Idea
Replication and consistency models are fundamental to building robust distributed systems. Replication ensures data availability by distributing it across multiple nodes, while consistency models determine how operations on shared data should be managed to maintain correctness.

## Frameworks Introduced
- **Quorum-based Availability**: Uses majorities of replicas to ensure consistent data availability even during failures.
  - When to use: High availability requirements or network partitions.
  - How: Implement a quorum system with replication factor N and write-quorum W, ensuring overlapping read and write quorums.

## Key Concepts
- **Replication Factor (N)**: Number of replicas storing the same data. Higher N increases availability but adds overhead.
- **Linearizability**: Operations appear as instantaneous linear time orderings across all processes.
- **Sequential Consistency**: Writes propagate in a global order, ensuring causally related operations are visible to clients.
- **Causal Consistency**: Ensures that causally related operations are observed in the same order by all processes.

## Mental Models
- Use replication when high availability is needed (e.g., distributed file servers).
- Think of quorum-based availability as a way to ensure data consistency despite node failures.

## Anti-patterns
- **Not using Quorum-based Availability**: Can lead to unavailability during network partitions.
  - Why it fails: Lack of guaranteed data availability in critical systems.

## Code Examples
```markdown
# Example: CRDT (Conflict-Free Replicated Data Types)
```
from typing import Any

class ReadWriteCounter:
    def __init__(self, n: int):
        self.n = n
        self.values = [0] * n

    async def read(self) -> list[int]:
        return [min(v, self.n) for v in self.values]

    async def write(self, delta: int, pos: int) -> None:
        if self.values[pos] + delta > self.n:
            raise ValueError("Write overflow")
        self.values[pos] += delta
```

## Reference Tables
| Consistency Model          | Availability Guarantees | Use Cases                          |
|----------------------------|---------------------------|-------------------------------------|
| **Linearizability**       | High                   | Strong consistency for transactional data centers |
| **Sequential Consistency**| Moderate                 | Shared state management systems    |
| **Causal Consistency**   | Low                    | Eventual consistent databases      |

## Key Takeaways
1. Use quorum-based availability when high availability is required.
2. Understand the trade-offs between consistency models to choose the right one for your system.
3. Avoid anti-patterns like not using replication in critical systems.

## Connects To
- Relates to distributed storage, replication strategies, and eventual consistency concepts discussed in later chapters.