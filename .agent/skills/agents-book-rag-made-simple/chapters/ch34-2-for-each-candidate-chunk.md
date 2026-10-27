# Chapter 34: Cross-Encoder Reranking

## Core Idea
Cross-encoder reranking improves query relevance by evaluating each chunk against the query using a specialized model designed for this task. While slightly slower than LLM-based methods, cross-encoders offer better accuracy and flexibility for complex queries.

## Frameworks Introduced
- **Cross-Encoder Reranking Algorithm**:
  - When to use: When high query relevance is critical, especially in domains like medical or legal knowledge bases.
  - How: Retrieve top-K candidates using a bi-encoder to filter noise, then feed each (query, chunk) pair through the cross-encoder model for precise scoring.

## Key Concepts
- **Cross-Encoder Model**: A small, task-specific model that evaluates query-document pairs directly for relevance.
- **Bi-Encoder**: Uses two separate encoders to represent queries and documents separately before feeding them into a joint model for comparison.
- **Query-Document Pair**: The input format for the cross-encoder model, consisting of a search query and a candidate chunk.

## Mental Models
- Use cross-encoder reranking when you need accurate relevance scoring for complex or nuanced queries. Think of it as a more precise but slightly slower alternative to LLM-based reranking.

## Anti-patterns
- **Avoid using cross-encoder reranking** when:
  - Query latency is extremely high.
  - The document collection is small, and retrieval quality doesn't need refinement.
  - Custom relevance criteria are required beyond what pre-trained models can capture.

## Code Examples
```python
def cross_encoder_rerank(query, chunks):
    # Bi-encoder retrieves top-K candidates (e.g., K=20)
    top_k_chunks = bi_encoder_retriever.retrieve(query, k=20)
    
    # Cross-encoder evaluates each query-chunk pair in batches
    scores = cross_encoder_model.predict([(query, chunk) for chunk in top_k_chunks])
    
    # Sort chunks by relevance score and select top-N (e.g., N=5)
    sorted_chunks = [chunk for _, chunk in sorted(zip(scores, top_k_chunks), reverse=True)]
    selected_chunks = sorted_chunks[:5]
    
    return selected_chunks
```

This pseudocode demonstrates how cross-encoder reranking processes multiple query-chunk pairs efficiently.

## Reference Tables

| Parameter                | Cross-Encoder Reranking       | LLM-Based Reranking        |
|--------------------------|-------------------------------|---------------------------|
| Query Latency            | Moderate to high              | Potentially higher latency  |
| Preparation Cost         | None                          | None                       |
| Accuracy Gain           | Significant for complex queries | Modest improvement          |
| Additional Latency       | Yes (batch processing)        | Yes (LLM prompt evaluation) |

## Key Takeaways
1. Use cross-encoder reranking when high query relevance is needed, especially in complex or nuanced domains.
2. Cross-encoders offer a balance between speed and accuracy for small candidate sets.
3. Opt for LLM-based reranking when you need maximum flexibility through custom prompts but are constrained by latency.

## Connects To
- Relates to chapter 3's relevancy grading, which focuses on binary filtering of low-quality chunks before reranking.
- Builds upon the bi-encoder approach discussed in earlier chapters for efficient query-document comparison.