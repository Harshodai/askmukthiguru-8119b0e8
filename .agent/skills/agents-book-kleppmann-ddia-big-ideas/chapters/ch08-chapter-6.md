# Chapter 8: Chapter 6

## Core Idea
The most important thing this chapter teaches is that **partitioning allows you to distribute data across multiple machines to handle large datasets efficiently**, avoiding monolithic systems and scaling challenges.

## Frameworks Introduced
- **Key-Range Partitioning**: Uses sorted keys, with each partition owning a contiguous range of keys.  
  - When to use: Suitable for ordered keys where range queries are common.
  - How: Sort the keys, then split them into ranges assigned to different partitions.

- **Hash-Based Partitioning**: Applies a hash function to keys, distributing data across partitions based on hash values.  
  - When to use: Appropriate when keys are not uniformly distributed or do not follow an order that lends itself to range queries.
  - How: Hash the key and assign it to a partition based on the hash value.

## Key Concepts
- **Partition Boundary**: The dividing line between two partitions, where data is stored.  
- **Rebalancing Partitions**: Adjusting the distribution of data across partitions when load imbalances occur or nodes are added/removed.
- **Hash Partitioning**: Uses a hash function to distribute data across multiple partitions.

## Mental Models
- Use consistent hashing when you need to minimize changes to partition assignments during rebalancing.  
  - Think of it as maintaining stable connections between key ranges and their assigned partitions.

## Anti-patterns
- **Hot Spots**: A situation where certain nodes handle disproportionately large portions of the data, leading to performance bottlenecks.
  - What to avoid: Failing to evenly distribute load or choose a partitioning strategy that matches query patterns.

## Code Examples
```
SELECT HASH(column_key) % num_partitions AS hash_partition,
      column_value
FROM table_name
PARTITION BY HASH(column_key);
```

This demonstrates how to use a hash-based partitioning approach in SQL, assigning each row to a partition based on the hash of its key.

## Reference Tables
| Framework          | When to Use                     | How                   |
|--------------------|----------------------------------|-----------------------|
| Key-Range Partitioning | Ordered keys with range queries | Sort keys and split into ranges |
| Hash-Based Partitioning | Non-uniform or unordered keys   | Hash the key and assign partitions |

## Key Takeaways
1. Choose partitioning strategy based on query patterns to avoid hot spots.
2. Use consistent hashing to minimize rebalancing effort when nodes change.
3. Rebalance partitions dynamically as load or node configurations change.

## Connects To
- Chapter 5: Distributed Systems Basics  
- Chapter 7: Replication Strategies