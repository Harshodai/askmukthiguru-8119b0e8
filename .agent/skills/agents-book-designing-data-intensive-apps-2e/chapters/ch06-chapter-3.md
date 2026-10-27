# Chapter 6: Chapter 3: Data Models and Query Languages

## Core Idea
The chapter emphasizes understanding different data models (relational, document, graph-based, event sourcing, and NewSQL) and their trade-offs in terms of structure, schema flexibility, use cases, and performance implications.

## Frameworks Introduced
- **Relational Model**: Uses tables with rows and columns; supports complex queries via SQL.
  - When to use: Structured data with regular schemas.
  - How: Defines relationships explicitly between entities using tables.
  
- **Document Model (JSON)**: Represents data as JSON documents, ideal for flexible schemas and lightweight data storage.
  - When to use: Flexible schema needs or hierarchical data representation.
  - How: Stores data in a single document with key-value pairs.

- **Graph-Based Data Models**: Uses nodes and edges to represent entities and relationships.
  - When to use: Complex, interconnected data (e.g., social networks).
  - How: Represents data as nodes connected by edges for semantic queries.

- **Event Sourcing**: Captures events alongside a base table for transactional storage.
  - When to use: Temporal or event-driven applications.
  - How: Stores events in a log and related data in a base table.

- **NewSQL Models**: Combine relational and NoSQL features for scalability and flexibility.
  - When to use: Scalable, distributed systems with complex queries.
  - How: Integrates relational schemas with document or graph structures.

## Key Concepts
- **Declarative Query Languages**: SQL, Cypher, SPARQL, Datalog— specify what to do without how.
- **Impedance Mismatch**: Object-Oriented apps often struggle with relational databases due to data model mismatches.
- **Normalization vs. Denormalization**: Normalized data uses unique IDs for fields; denormalized stores human-readable data redundantly.

## Mental Models
- Use the **relational model** when you need structured, explicit relationships between entities.
- Think of the **document model** as a flexible way to represent data with JSON or XML.
- Consider **graph-based models** for complex, interconnected datasets like social networks.
- Plan for **event sourcing** in applications where temporal data and transactions are critical.
- Leverage **NewSQL** for modern, scalable systems that combine relational and NoSQL benefits.

## Anti-patterns
- **Object-Relational Mismatch**: Using ORMs can lead to inefficiencies if schema flexibility isn't managed well.
  - Why it fails: Inconsistent or inefficient queries due to impedance mismatches between app code and database models.

## Code Examples
```python
# Example SQL query using the relational model
SELECT users.first_name, users.last_name FROM users WHERE users.user_id = '123';

# Example JSON document using the document model
{
  "user_id": "456",
  "first_name": "John",
  "last_name": "Doe"
}
```

## Reference Tables

| Data Model          | Structure                          | Use Cases                                  |
|---------------------|------------------------------------|--------------------------------------------|
| Relational         | Tables (rows, columns)             | Structured data with explicit relationships   |
| Document            | JSON/XML documents                 | Flexible schemas, hierarchical data        |
| Graph              | Nodes and edges                     | Social networks, recommendation systems     |
| Event Sourcing      | Log of events + base table          | Temporal data, transactional storage       |
| NewSQL             | Relational + document/graph        | Scalable, distributed systems             |

## Key Takeaways
1. Choose the right data model based on your application's needs and complexity.
2. Understand trade-offs between query performance (relational) vs. schema flexibility (document).
3. Leverage declarative languages for clean, maintainable queries.

## Connects To
- Database Design Principles
- Query Optimization Techniques
- Application Architecture Decisions