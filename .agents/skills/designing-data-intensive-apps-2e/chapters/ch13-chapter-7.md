# Chapter 13: Sharding  
## Core Idea  
Sharding is essential for scaling modern applications by distributing data across multiple machines. It allows you to scale out your database operations while maintaining acceptable performance levels.

## Frameworks Introduced  
- **Key-Shard**: Uses key ranges to assign records to shards, ensuring consistent routing but requiring range queries on each shard.
  - When to use: Suitable for workloads with predictable access patterns and hotspots that can be mitigated by partitioning data logically.
  - How: Partition the dataset into contiguous ranges based on the primary key, creating a separate shard for each range. Shard assignment is done at insertion time using the partition key.

- **Hash-Shard**: Distributes records across shards based on a hash function of the partition key, reducing hotspots and improving query performance.
  - When to use: Ideal for workloads with unpredictable access patterns or high read-heavy workloads that benefit from balanced distribution.
  - How: Compute a consistent hash value for each record's partition key. Shard assignment is done at insertion time using the hash value.

- **Raft**: A distributed database management system designed for sharded architectures, providing efficient range queries and hot-touch operations.
  - When to use: For high availability and strong consistency in large-scale applications requiring both read and write performance.
  - How: Uses a token-based approach with a balanced tree structure to manage shard assignments efficiently.

## Key Concepts  
- **Partition Key**: The column used to partition data across shards, ensuring consistent routing of queries.  
- **Shard**: A subset of the database containing records assigned to a specific range or hash value based on the partition key.  
- **Load Balancing**: Ensures that no single shard is overwhelmed with too much work by distributing operations evenly across all active nodes.

## Mental Models  
- Use Key-Shard when your application has predictable access patterns and needs to handle hotspots.
- Think of Hash-Shard as a way to distribute data more evenly while maintaining consistent query performance, especially for read-heavy workloads.

## Anti-patterns  
- Avoid rebalancing the sharded cluster without considering the impact on write operations. This can lead to inconsistencies in workload distribution and degraded performance.
- Do not use Key-Shard without also implementing partition keys for secondary indexes when dealing with range queries or high read-heavy workloads, as it increases storage costs.

## Code Examples  
```python
from sharded import Shard

shards = 10
index = 0

def assign_shard(record):
    index = hash(record[KEY].toString()) % shards
    return Shard(index)
```

This example demonstrates assigning records to shards based on the hash of their partition key, ensuring even distribution across the cluster.

## Reference Tables  
| **Parameter**         | **Relevant Framework** | **Description**                                                                 |
|-----------------------|-------------------------|-----------------------------------------------------------------------------|
| Number of Partitions  | Key-Shard               | Determines how many ranges to split the dataset into.                          |
| Load Balancing Frequency | Hash-Shard             | How often to rebalance the distribution of data across shards.              |
| Algorithm for Load Balancing | Raft                  | Uses a token-based approach to ensure balanced and consistent shard assignment.

## Key Takeaways  
1. Use Key-Shard when your application has predictable access patterns and needs to handle hotspots.
2. Optimize query performance by using Hash-Shard or Raft, depending on your workload characteristics.
3. Always implement partition keys for secondary indexes to maintain efficient range queries across shards.
4. Balance the load by periodically rebalancing your sharded cluster based on current workloads.

## Connects To  
- Chapter 6: Partitioning (for understanding how partitions relate to sharding)
- Chapter 8: Load Balancing and Capacity Planning (for managing distribution of operations)