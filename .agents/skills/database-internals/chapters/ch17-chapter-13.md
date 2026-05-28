```markdown
# Chapter 17: CHAPTER 13

## Core Idea
Distributed transactions ensure atomicity, consistency, availability, and performance across distributed systems by leveraging consensus algorithms like two-phase commit (2PC) and three-phase commit (3PC), as well as advanced methods such as Calvin, Spanner, and Percolator.

## Frameworks Introduced
- **Two-Phase Commit (2PC)**: A simple atomicity mechanism requiring a prepare phase followed by a confirm phase.  
  - When to use: When simplicity is preferred over availability guarantees.
  - How: Cooperates with a transaction manager to handle coordination and failure recovery.

- **Three-Phase Commit (3PC)**: An enhanced version of 2PC that handles network partitions by allowing a coordinator to act as a leader in the second phase.  
  - When to use: In distributed systems where availability is critical.
  - How: Uses a pseudo-leader for coordination and failure recovery.

- **Coordination Avoidance**: A technique that allows operations to proceed without full coordination, preserving performance while maintaining consistency.  
  - When to use: When minimizing coordination overhead is crucial.
  - How: Implements read atomicity and invariant-based coordination.

## Key Concepts
- **Two-Phase Commit (2PC)**: Consists of a prepare phase for acquiring locks and a confirm phase for releasing them after a transaction is committed.
- **Three-Phase Commit (3PC)**: Includes an additional phase to handle coordinator failures, ensuring atomicity even in network partitions.
- **Calvin**: A distributed transaction management system using optimistic concurrency control with pessimistic rollback.
- **Spanner**: Uses consistent hashing and two-phase locking for atomic transactions across replicated data stores.
- **Percolator**: Implements snapshot isolation using a transactional API on top of a distributed database.

## Mental Models
- Use 2PC when you need atomicity but are willing to sacrifice availability in certain scenarios.
- Use advanced methods like Calvin or Percolator when high performance and fault tolerance are required.
- Think of coordination avoidance as enabling partially ordered sets (POSets) for efficient transaction management.

## Anti-patterns
- **Not having a leader in 2PC**: This can lead to network partitions causing transaction splits, where some nodes miss out on commits or aborts.
- **Using optimistic concurrency control without atomicity guarantees**: This can result in data inconsistencies and anomalies like read skew.

## Code Examples
```key code example
1. Transaction coordinator in pseudo-code:
   ```
   function transactional-coordinate (parameters) {
     prepare  phase;
     if (success) {
       commit  phase;
     } else {
       abort;
     }
   }
   ```

   This demonstrates the basic structure of a transaction coordinator, showing how it manages prepare and commit phases to ensure atomicity.

## Reference Tables
| Framework          | Key Mechanism                          |
|--------------------|-------------------------------------------|
| Two-Phase Commit (2PC) | Uses prepare/confirm phases for atomicity    |
| Three-Phase Commit (3PC) | Handles network partitions with a pseudo-leader  |
| Calvin              | Combines optimistic concurrency control with pessimistic rollback   |
| Spanner             | Uses consistent hashing and two-phase locking  |
| Percolator          | Implements snapshot isolation using lock-based coordination |

## Key Takeaways
1. Use 2PC for simplicity in systems where availability is a concern.
2. Leverage advanced methods like Calvin or Percolator for high-performance, fault-tolerant systems.
3. Avoid premature coordination to optimize performance and scalability.

## Connects To
- Consensus algorithms (next chapter)
```