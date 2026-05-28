# Chapter 8: Storage and Retrieval

## Core Idea
PostgreSQL's storage architecture is designed to optimize performance and scalability, using B-trees for traditional indexing, hash tables for quick lookups, and advanced structures like LSMs and HNSW for efficient similarity search. The chapter emphasizes the importance of choosing appropriate data structures based on query patterns and dataset characteristics.

## Frameworks Introduced
- **B-tree Index**: Used for ordered key-value storage in traditional databases.
  - When to use: For sequential access or range queries.
  - How: Implements a hierarchical tree structure with B nodes, supporting logarithmic time complexity for insertions, deletions, and searches.

- **Hash Table (Bloom Filter)**: Uses hashing to store approximate set membership.
  - When to use: For membership testing in large datasets.
  - How: Implements Bloom filters with bitarrays for efficient space and time trade-offs.

- **Merkle Tree**: Used for efficient range queries on sorted data.
  - When to use: For retrieving a subrange of records.
  - How: Builds a binary tree structure over sorted values, enabling fast prefix-based queries.

- **LSM (Log Structured Merge)**: Uses multiple sorted files for efficient storage and retrieval.
  - When to use: For large datasets requiring high performance.
  - How: Stores data in fixed-width blocks across multiple files, supporting parallel I/O and cache efficiency.

- **HNSW (Hierarchical Navigative Search)**: Utilizes graph-based indexing for approximate nearest neighbor search.
  - When to use: For high-dimensional similarity search.
  - How: Constructs a hierarchical navigable small-world graph with multiple layers of connections.

## Key Concepts
- **B-trees**: Optimal for ordered data, supporting efficient range queries and insertions.
- **Hash Tables**: Provide fast lookups at the cost of memory overhead.
- **Merkle Trees**: Enable efficient range queries on sorted data.
- **LSMs**: Offer high throughput with low latency for large datasets.
- **HNSW**: Provides a scalable solution for high-dimensional similarity search.

## Mental Models
1. Use B-trees when your application requires fast sequential access and range queries.
2. Opt for hash tables when dealing with membership testing in large datasets.
3. Choose Merkle trees for efficient prefix-based queries on sorted data.
4. Apply LSMs for high-performance storage of massive datasets.
5. Use HNSW for advanced similarity search in high-dimensional spaces.

## Anti-Patterns
1. Avoid using B-trees for unordered or random access patterns, as they are inefficient for such use cases.
2. Do not rely solely on hash tables for membership testing without considering dataset size and query frequency.
3. Steer clear of Merkle trees when the data does not support efficient range queries.

## Code Examples
```python
# Example of B-tree implementation in PostgreSQL
CREATE TABLE user_data (
    id bigint primary key,
    name text,
    age integer
);

CREATE INDEX b_tree_idx ON user_data USING btree(order by name);
```

```sql
-- Example of Merkle tree construction
CREATE TABLE user_data_merkle (
    id bigint,
    name text,
    age integer,
    index struct (md5(name) ASC)
);

CREATE INDEX merkli_index ON user_data_merkle USING hstore;
```

## Reference Tables
| Framework | Key Features |
|---|---|
| B-tree | Supports ordered data, range queries, and fast insertions/deletions. |
| Hash Table | Provides O(1) average lookup but limited to hash-based keys. |
| Merkle Tree | Efficient for prefix queries on sorted data. |
| LSM | High throughput with multiple sorted files for large datasets. |
| HNSW | Effective for high-dimensional similarity search. |

## Key Takeaways
1. Choose the appropriate index based on query patterns and dataset characteristics.
2. Optimize storage structures for specific applications like web search or transactional databases.
3. Avoid over-reliance on single data structures without considering their limitations.

## Connects To
- Chapter 5: Query Optimization
- Chapter 6: Data Modeling
- Chapter 7: Transaction Management