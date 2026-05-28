# Chapter 33: Reranking

## Core Idea
Reranking improves the accuracy of retrieved chunks by evaluating them more thoroughly after initial retrieval.

## Frameworks Introduced
- **Reranking Pipeline**: A two-stage process that combines retrieval and evaluation, inspired by hiring practices.  
  - When to use: When you need to enhance retrieval accuracy in RAG systems.
  - How: Retrieve a broad set of candidates (e.g., top 10-30) and evaluate each with a reranker.

## Key Concepts
- **Reranker**: A system that evaluates candidate chunks after retrieval, improving relevance.
- **Bi-Encoder**: A model processing query and document independently, relying on vector similarity.
- **Cross-Encoder**: A model processing query and document together for joint relevance detection.
- **LLM-based Reranking**: Uses prompts to score how well a chunk answers the query.

## Mental Models
- Use reranking pipeline when you need accurate retrieval in large document collections.  
  - Think of reranking as a hiring process that narrows down candidates based on their relevance.

## Anti-patterns
- **Over-reliance on embeddings**: Bi-encoders are not suitable for reranking due to their independence between query and documents.
  - Why it fails: They miss fine-grained interactions between text and query, leading to inaccurate evaluations.

## Code Examples
```python
# Example prompt for LLM-based reranking
def get_relevance_score(query: str, chunk: str) -> float:
    """Evaluates how well the chunk answers the query."""
    return modelEvaluate(
        f"Rate relevance of this passage to '{query}': {chunk}. "
        "Use a scale from 0 (no relevance) to 10 (perfect answer)."
    )
```

## Reference Tables
| Framework       | Architecture                          | Use Case                     |
|-----------------|----------------------------------------|------------------------------|
| Bi-Encoder       | Independent query and document vectors | Fast vector search           |
| Cross-Encoder   | Joint processing of query and doc     | Reranking for small sets      |

## Key Takeaways
1. Use reranking to improve the accuracy of retrieved chunks.
2. Retrieve a broad set of candidates (e.g., top 10-30) before evaluation.
3. Avoid using bi-encoders for reranking due to their limitations in capturing query-document interactions.
4. Leverage LLMs effectively by designing prompts that capture relevance signals.

## Connects To
- Relates to Chapter 1: Embeddings, Vector Search, and Basic RAG Pipeline  
- Connects to upcoming discussions on fusion retrieval