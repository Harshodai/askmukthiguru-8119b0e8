```markdown
# Chapter 11: CHAPTER 6

## Core Idea
Replication is essential for building robust distributed systems that handle failures, scalability, and latency issues. Single-leader replication provides strong consistency but requires careful handling of replication lag and node failures.

## Frameworks Introduced
- **Single-Leader Replication**: 
  - When to use: When a single leader node is sufficient for high availability and strong consistency.
  - How: Write directly to the leader, have other nodes confirm updates via replication logs or checkpoints. Fallback involves replicating logs or using a failover process.

## Key Concepts
- **Replication Lag**: Time delay between writes and their acknowledgment by followers.
- **Monotonic Reads**: Ensure data is not seen in reverse order across reads.
- **Consistent Prefix Reads**: Preserve the order of reads relative to writes for consistency.

## Mental Models
- Use single-leader replication when you need strong consistency but can tolerate some node failures. Think of it as replicating to one leader for high availability, similar to how a traditional database might back up its data.

## Anti-patterns
- Avoid split brain by ensuring a primary node is elected and replicated before failure. Do not use all followers for writes due to performance overhead in large systems.

## Code Examples
```python
# Example from PostgreSQL replication logic (simplified)
def send_replication_log replicator:
    # Steps to replicate log to followers
    replicator.send_to_replication_log(log)
```

This demonstrates how a replication log is sent to other nodes for consistency.

## Reference Tables
| **Factor**              | **Single-Leader Replication**                  | **Multi-Leader Replication**                   |
|--------------------------|--------------------------------------------------|-----------------------------------------------|
| Availability             | High (single node failure handled by failover)    | Depends on replication strategy and network |
| Partition Tolerance     | None                                              | Can handle partitioned data with sharding       |
| Latency                  | Low ( Ideally 0.1–0.2 ms for local writes )      | Higher due to multiple write paths              |

## Key Takeaways
1. Understand the trade-offs between strong consistency and replication lag.
2. Use single-leader replication when you need strong consistency but can tolerate some node failures.
3. Choose appropriate replication strategies based on network reliability and availability requirements.
4. Avoid anti-patterns like split brain by ensuring a primary is elected and replicated before failure.

## Connects To
- The 5 Whys of replication lag (Chapter 9)
- Distributed systems concepts (Chapter 10)
```