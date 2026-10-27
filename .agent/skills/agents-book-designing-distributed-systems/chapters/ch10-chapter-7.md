# Chapter 10: Sharded Services

## Core Idea
Sharding allows distributing data across multiple services to enhance scalability, performance, and fault tolerance by partitioning data and traffic among multiple machines.

## Frameworks Introduced
- **Sharded Caching**: A design pattern for building sharded services where data is distributed across multiple cache instances.
  - When to use: When scaling a service beyond the capacity of a single machine.
  - How: Partition data into shards, each served by its own cache or replicated service.

## Key Concepts
- **Shard**: A portion of data or traffic assigned to a specific machine or service.
- **Sharding Function**: A mechanism that maps requests to specific shards based on a hash key (e.g., request path).
- **Consistent Hashing**: A hashing technique that minimizes remapping when scaling by using load balancing algorithms like "round-robin."
- **Hot Shards**: Cache shards experiencing disproportionately high traffic that require special handling.

## Mental Models
- Use consistent hashing when distributing data across multiple services to minimize failures during scaling.
- Think of sharded caching as isolating subsets of your application's state while maintaining overall performance and availability.

## Anti-patterns
- **Poorly designed sharding functions**: Can lead to cache inconsistencies or hot shard failures if not properly accounted for during scaling.

## Code Examples
```kubernetes
# Example Sharded Cache Configuration (Reference: Chapter 7)
```