# Chapter 8: Search Engine Architecture Design

## Core Idea
This chapter outlines the design principles for building a high-performance search engine that combines traditional search techniques with advanced AI/ML models to enhance relevance, personalization, and efficiency.

## Frameworks Introduced
- **Hybrid Search Pipeline**: Combines low-cost (P90) and high-cost (P99) retrieval paths.
  - When: To balance speed and accuracy for different user intents.
  - How: Low-cost embeddings for P90 and full-text LLM queries for P99.

## Key Concepts
- **Vector Search**: Represents documents as vectors for efficient similarity search using FAISS.
- **Caching**: Implements LRU strategy with time-based keys (HNSW graph) to reduce latency.
- **Partitioned Caching**: Uses horizontal scaling across AZs for high availability.
- **P90 vs P99 Paths**: Different retrieval strategies based on query confidence.

## Mental Models
- Use FAISS when you need fast vector similarity search.
  - Think of it as a graph-based nearest neighbor model optimized for large-scale data.

## Anti-patterns
- Avoid monolithic architectures without horizontal scaling.
  - Why it fails: Lack of fault tolerance and poor scalability.

## Code Examples
```python
# Example of implementing P90 and P99 paths using LangChain and HuggingFace

from langchain import LlamaCpp
import faiss
from transformers import SimilarityScore

def hybrid_search_pipeline(query):
    # P90 Path: Fast vector search
    results_p90 = vector_search(query, k=10)
    
    # P99 Path: High-cost LLM retrieval
    prompt = "Which of these products best matches your query?"
    response = model.chat asking prompt with examples
    
    return combine_results(results_p90, response)

def vector_search(query, k=5):
    # Use FAISS for fast vector similarity search
    scores = model.vector_search(query, k=k)
    return format_results(scores)

# Example decision matrix
decision_matrix = {
    "Top Score": [0.8, 0.6],
    "Fallback Trigger": [0.4, None]
}

if top_score < 0.5:
    trigger_llm(rewrite_query)
```

## Reference Tables
| Metric        | P90 Performance | P99 Performance |
|---------------|-----------------|------------------|
| Latency (ms)   | 100              | 300              |
| Throughput     | 500/s           | 20/s            |

## Key Takeaways
1. Use hybrid search paths to balance speed and accuracy.
2. Optimize caching strategies for high availability.
3. Leverage AI/ML models for personalization without sacrificing performance.

## Connects To
- Chapter 7: Search Engine Architecture Design
- Chapter 9: Efficiency and Scalability