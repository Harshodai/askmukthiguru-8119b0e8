# Chapter 51: 1. Split documents into text chunks  

## Core Idea  
Graph RAG (Retrieval-Augmented Generation) organizes large document corpora into structured knowledge graphs, enabling efficient retrieval and summarization of information at multiple granularity levels.

## Frameworks Introduced  
- **Knowledge Graph Construction**:  
  - Formulation: Extract entities and relationships from document chunks using LLMs.  
  - When to use: For building a graph representation of interconnected data.  
  - How: Process each chunk, identify nodes (entities) and edges (relationships), and link them together.

## Key Concepts  
- **Knowledge Graph**: A network where entities are nodes and relationships are edges.  
- **Community Summaries**: Precomputed summaries for clusters of related entities at different hierarchy levels.  
- **Local Search**: Queries focused on specific entities or their immediate context, traversing the graph outward.  
- **Global Search**: Queries addressing broad themes or patterns across the knowledge base using community summaries.

## Mental Models  
- Use a knowledge graph when you need to connect information scattered across documents.  
- Think of communities as high-level themes or clusters of related entities for holistic queries.

## Anti-patterns  
- **Avoid standard RAG**: When your users ask questions that require understanding connections between passages, stick with Graph RAG instead of relying solely on individual chunk retrieval.

## Code Examples  
```python
# Example community summarization process
def summarize_community(community):
    """Pre-compute a summary for a community of entities."""
    context = [chunk for _, chunk in community]
    summary = LLM.generate_summary(context)
    return summary

# Example local search implementation
def local_search(query):
    """Retrieve and traverse entities related to the query."""
    entities = extract_entities(query)
    graph = knowledge_graph
    traversal = traverse_graph(entities, graph)
    return process_traversal(traversal)
```

## Reference Tables  

| Parameter          | Value/Description                                                                 |
|--------------------|-----------------------------------------------------------------------------------|
| Indexing Cost      | High due to LLM processing of every chunk and community summarization.        |
| Query Latency      | Low for local search; high for global search (map-reduce over summaries).       |
| Accuracy Gain     | Large for cross-document queries; minimal for simple fact lookups.              |

## Key Takeaways  
1. Use Graph RAG when you need to handle large corpora with rich entity relationships and users asking both specific and big-picture questions.  
2. Community detection at multiple hierarchy levels is crucial for enabling holistic query answering.  
3. Local search is ideal for targeted queries, while global search excels at broad thematic exploration.

## Connects To  
- Relates to knowledge graph construction techniques in Chapter 50.  
- Connects with community detection methods discussed in Chapter 49.