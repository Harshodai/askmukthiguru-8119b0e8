# Chapter 7: Data Models and Query Languages

## Core Idea
The single most important thing this chapter teaches is the importance of selecting an appropriate data model that aligns with your application's requirements, query patterns, and scalability needs.

## Frameworks Introduced
- **Relational Model**: Uses structured tables and SQL queries. Best for relational data and traditional applications.
  - When to use: When dealing with tabular data and complex hierarchical relationships.
  - How: Organize data in tables with rows (records) and columns (fields), using SQL for querying.

- **Document Store**: Represents data as documents with properties. Ideal for semi-structured or unstructured data.
  - When to use: For flexible, unstructured data like text, images, or logs.
  - How: Documents are stored as JSON objects with named properties, queried using XPath or NoSQL databases.

- **Graph Database**: Models data as nodes and relationships. Suitable for complex, connected, and network-based data.
  - When to use: For social networks, recommendation systems, or data with inherent relationships (e.g., user interactions).
  - How: Represents entities as nodes and their connections as edges, queried using graph-specific languages like Cypher.

- **Property Graph Model**: Combines the strengths of relational and graph models. Uses properties for both nodes and edges.
  - When to use: For data requiring both tabular and network analysis capabilities.
  - How: Nodes represent entities with attributes, edges represent relationships with properties, queried using SPARQL or Cypher.

- **Spatial Data Model**: Designed for geospatial data, storing coordinates and spatial relationships.
  - When to use: For applications involving geographic information (e.g., mapping services).
  - How: Stores latitude/longitude points in specialized tables, supporting operations like distance calculations.

## Key Concepts
- **Relational Model**: Tabular structure with rows and columns. Supports joins, views, and transactions using SQL.
- **Document Store**: Flexible storage for semi-structured data. Supports property-based queries and NoSQL databases.
- **Graph Database**: Represents data as nodes and edges. Queries use graph patterns (e.g., shortest path algorithms).
- **Property Graph Model**: Combines relational and graph capabilities with properties on both nodes and edges.
- **Spatial Data Model**: Stores geospatial coordinates for mapping and proximity queries.

## Anti-patterns
- Using a relational model for highly connected or complex network data.
- Neglecting to index time-series data for efficient querying.
- Overcomplicating queries with joins when simple lookups suffice.
- Ignoring data type-specific optimizations (e.g., using JSON for binary data).

## Code Examples
```python
# Example of using NetworkX for graph analysis
import networkx as nx
G = nx.erdos_renyi_graph(10, 0.5)
print(f"Number of nodes: {G.number_of_nodes()}")
print(f"Number of edges: {G.number_of_edges()}")
```

This code demonstrates creating a random graph and querying its properties using NetworkX.

## Reference Tables
| Data Model          | Key Features                                      | Use Case Scenarios                     |
|---------------------|----------------------------------------------------|-----------------------------------------|
| Relational Model    | Tabular structure, SQL queries                   | Relational databases, transactional data       |
| Document Store     | Semi-structured data storage, XPath/NoSQL queries | Textual data, unstructured documents        |
| Graph Database      | Network-based data, graph patterns                | Social networks, recommendation systems   |
| Property Graph    | Combines relational and graph capabilities       | Tabular + network analysis applications  |
| Spatial Model     | Geospatial data storage, proximity queries         | Mapping services, location-based apps |

## Key Takeaways
1. Choose a data model based on your application's needs: relational for tabular data, document stores for semi-structured data, graph databases for networks, and property graphs for combined needs.
2. Optimize query patterns by selecting appropriate models that support efficient operations (e.g., joins vs. path queries).
3. Consider performance tradeoffs when choosing between NoSQL and relational databases.
4. Use graph-specific tools like NetworkX or Neo4j for complex network analysis tasks.

## Connects To
- Relational databases, document stores, graph databases, and event sourcing models.