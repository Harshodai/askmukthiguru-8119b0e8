# Chapter 21: Graph RAG

## Core Idea
Graph RAG transforms document collections into knowledge graphs for enhanced retrieval capabilities. Instead of relying on vector similarity alone, it structures information through entities, relationships, and communities to answer both specific and broad questions effectively.

## Frameworks Introduced
- **Graph RAG**: A framework that builds knowledge graphs from documents to improve retrieval accuracy by leveraging structured relationships.
  - When to use: When dealing with big-picture questions or when chunk-based retrieval fails to capture implicit connections.
  - How: By extracting entities, building a graph of relationships, detecting communities, and summarizing them for quick access.

## Key Concepts
- **Knowledge Graph**: A network where nodes represent entities (people, places, concepts) and edges represent their relationships.
- **Community Detection**: The process of identifying densely connected subgraphs within the knowledge graph.
- **Entities**: Named elements in the graph, such as people, locations, or events.
- **Relationships**: Connections between entities, indicating how they are linked.
- **Summaries**: Precomputed descriptions of communities for quick synthesis during queries.

## Mental Models
- Use knowledge graphs when you need to answer questions that span across documents. Think of relationships as the threads connecting information.
- Communities represent themes or clusters of related concepts within your knowledge base.

## Anti-patterns
- Avoid sparse connection graphs where entities are too isolated, leading to incomplete answers. This happens when relationships between chunks are not adequately captured during indexing.

## Code Examples
```python
# Example entity extraction from a chunk
chunk = "The cybersecurity team identified potential risks in the supply chain."
entities = extract_entities(chunk)
print(entities)  # [{'name': 'Cybersecurity Team', 'type': 'organization'}, {'name': 'Supply Chain', 'type': 'system'}]
```

## Reference Tables
| Parameter | Description |
|---|---|
| Community Detection Algorithm | Leiden algorithm for optimal community detection |
| Resolution Parameter | Controls community granularity, e.g., `res=1` for broader communities |

## Key Takeaways
1. Graph RAG addresses the limitations of traditional retrieval by leveraging structured knowledge graphs.
2. Communities provide a hierarchical view of related concepts, enabling comprehensive answer synthesis.
3. Pre-computed summaries allow efficient retrieval of broad themes without reprocessing.

## Connects To
- Relates to chunk-based retrieval and proposition chunking as foundational techniques for Graph RAG.