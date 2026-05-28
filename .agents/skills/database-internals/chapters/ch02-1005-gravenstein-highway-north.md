# Chapter 2: 1005 Gravenstein Highway North

## Core Idea
This chapter provides a comprehensive overview of storage engines in database management systems, emphasizing their role in data persistence and their impact on system performance.

## Frameworks Introduced
- **Storage Engine Model**: Defines the structure and function of a storage engine, highlighting its interaction with higher-level subsystems.
  - When to use: When designing or selecting a database system.
  - How: Implements APIs for CRUD operations while managing data in memory and on disk.

## Key Concepts
- **OLTP (Online Transaction Processing)**: Focuses on read-heavy workloads with update capabilities, typically used for transactional applications.
- **TPC-C Benchmark**: A widely-used OLTP benchmark evaluating database performance under various transaction types.
- **YCSB**: A framework for benchmarking data stores using customizable workloads.

## Mental Models
- Use a storage engine when you need reliable and persistent data storage with efficient CRUD operations. Think of it as the backbone that ensures data integrity while enabling application functionality.

## Anti-patterns
- **Using deprecated databases**: Avoid outdated systems like MyRocks, which may have known issues or be non-suitable for modern applications.

## Code Examples
```markdown
```
- **What it demonstrates**: The use of TPC-C benchmarks to evaluate database performance in real-world scenarios.
```

## Reference Tables
| Database | Storage Engine Used        |
|----------|---------------------------|
| MySQL    | InnoDB, MyISAM            |

## Key Takeaways
1. Understand the workload characteristics (schema size, number of clients, query types) before selecting a storage engine.
2. Conduct thorough testing using benchmarks like TPC-C and YCSB to evaluate performance metrics.
3. Be prepared for potential migration challenges due to differences in storage engine implementations.

## Connects To
- Relates to database selection strategies discussed later in the book.