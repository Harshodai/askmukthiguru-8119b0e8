# Chapter 6: Replication

## Core Idea
This chapter explores various replication strategies for maintaining data consistency across distributed systems, focusing on algorithms like Raft, DynamoDB, HBase, and TiDB. It emphasizes the importance of replication in ensuring data availability, fault tolerance, and consistent writes even under high latency or partition failures.

## Frameworks Introduced
- **Raft**: A simple, sequential leader election algorithm for replicating writes to a single leader node.
  - When to use: Suitable for systems requiring simplicity and ease of implementation.
  - How: Leaders handle writes sequentially, with other nodes following in order.
  
- **DynamoDB**: Uses a distributed key-value store with flexible replication strategies based on quorum intersection.
  - When to use: Ideal for systems needing high availability and fault tolerance without strict partition recovery requirements.
  - How: Nodes replicate data based on overlapping sets of peers.

- **HBase**: Employs the Replication Protocol, which replicates writes across multiple nodes in a way that ensures consistency even with node failures.
  - When to use: Best for systems requiring high availability and fault tolerance with minimal replication overhead.
  - How: Uses a version vector mechanism to detect concurrent writes and ensure data consistency.

- **TiDB**: Implements Conflict-Causal Replication (CCR), which uses causal casts to handle write conflicts and maintain monotonicity in replicated data.
  - When to use: Suitable for systems requiring ordered writes and conflict resolution without manual coordination.
  - How: Uses vector clocks to detect causality between events and ensure consistent ordering.

## Key Concepts
- **Raft Algorithm**: Consensus algorithm where nodes vote on a single leader, which can change dynamically. It ensures sequential writes but struggles with high latency or failures.
  
- **DynamoDB's Quorum Intersection**: Nodes replicate data based on overlapping peer sets to achieve availability and fault tolerance without requiring global replication.

- **Replication Protocol**: A protocol-based approach where nodes replicate writes across multiple peers, ensuring consistency even in the face of node failures.

- **Conflict-Causal Replication (CCR)**: Uses vector clocks or causal casts to detect conflicts between concurrent writes and maintain consistent ordering in replicated data.

## Mental Models
- Use Raft when your system requires a single leader for write operations but needs simplicity.
- Use DynamoDB when you need high availability and fault tolerance without strict partition recovery requirements.
- Use TiDB's CCR approach when you prioritize ordered writes and conflict resolution over replication overhead.

## Anti-patterns
- **Replication Lag**: Avoid using multiple leaders or complex coordination mechanisms that introduce delays in data consistency.
- **Manual Replication**: Steer clear of manual replication strategies due to the complexity and potential for inconsistency.

## Code Examples
```java
// Example code from TiDB's CRR implementation
public static class CRTP {
  private final int[] causalSequence;
  private final int[][] versionVectors;
  
  public void write(Timestamp t, String key, String value) throws IOException {
    if (isLeader()) {
      if (!hasVersion(causalSequence, key)) {
        addVersion(key, version);
        commit();
        return;
      }
    }

    // Replicate to the first follower
    Follower replica = getFollower(key);
    if (replica != null) {
      replica.write(t, key, value);
      return;
    }

    // If no replication is possible, write directly
    if (!isReplicated(key)) {
      writeDirect(t, key, value);
      return;
    }

    // Otherwise, replicate to all followers and commit
    for (int i = 0; i < size(); i++) {
      replica[i].write(t, key, value);
    }
    
    commit();
  }
}
```

## Reference Tables
| **Decision Table: Choosing a Replication Strategy** |
|----------------------------------------------------|
| **Availability Goal** | **Recommended Algorithm** |
| High Availability with Partition Tolerance       | DynamoDB or TiDB (Quorum Intersection)        |
| Full Availability without Partition Tolerance      | Raft or Riak (Sequential Leader Election)         |
| Simplest Implementation                              | Raft or Raft-based Systems                   |

## Key Takeaways
1. Replication is essential for maintaining data availability and fault tolerance in distributed systems.
2. The choice of replication strategy depends on the system's requirements, such as availability goals and partition recovery needs.
3. Algorithms like Raft, DynamoDB, HBase, and TiDB offer different trade-offs between consistency, performance, and complexity.

## Connects To
- Relates to concepts from Chapter 5 on Availability and Consistency Models
- Connects to more advanced topics in eventual consistency models discussed in later chapters