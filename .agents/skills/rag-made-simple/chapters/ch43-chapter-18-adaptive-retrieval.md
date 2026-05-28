# Chapter 18: Adaptive Retrieval

## Core Idea
Adaptive retrieval optimizes information retrieval by categorizing queries into specific types (Factual, Analytical, Opinion, Contextual) and applying tailored strategies for each type.

## Frameworks Introduced
- **Triage System**: A triage system used in healthcare to route patients to the right specialist. Applied here to route queries to appropriate retrieval strategies.
  - When to use: When queries vary significantly in their requirements (factual vs analytical vs opinion-based).
  - How: Classify each query into one of four types and apply corresponding retrieval strategies.

## Key Concepts
- **Factual Query**: Seeks specific, verifiable information. Example: "What is the maximum upload size?"
- **Analytical Query**: Requires comprehensive analysis across multiple aspects. Example: "How do our caching strategies affect latency under different load patterns?"
- **Opinion Query**: Asks for subjective viewpoints or diverse opinions. Example: "What are the main arguments for and against microservices?"
- **Contextual Query**: Depends on user-specific circumstances. Example: "Based on my team’s current architecture, which database should we migrate to?"

## Mental Models
- Use vector search when you need precise factual information.
  - Think of vector search as a tool for retrieving exact matches in a document space.

## Anti-patterns
- **Avoid one-size-fits-all retrieval**: This approach fails when queries vary significantly in their requirements (factual vs analytical vs opinion-based).

## Code Examples
```python
# Example code to enhance and retrieve relevant passages for a factual query
def enhance_query(query):
    """Rewrite the original query into a more precise form optimized for retrieval."""
    return enhanced_query

def get_factual_passages(query, k=2000):
    """Factual Retrieval Strategy: Precision Through Enhancement and Ranking"""
    enhanced = enhance_query(query)
    candidates = vector_store.similarity_search(enhanced, k=k*2)
    scores = relevance_model.score_documents(candidates, enhanced)
    top_k = [candidate for _, candidate in sorted(zip(scores, candidates), key=lambda x: -x[0])[:k]]
    return top_k
```

## Reference Tables

| Query Type         | Retrieval Strategy                          |
|--------------------|-----------------------------------------------|
| Factual            | Precision Through Enhancement and Ranking  |
| Analytical          | Decomposed into sub-questions for comprehensive coverage |
| Opinion            | Viewpoint-aware retrieval seeking diversity   |
| Contextual         | Reformulated with user-specific information    |

## Key Takeaways
1. Classify queries into specific types (Factual, Analytical, Opinion, Contextual) to optimize retrieval strategies.
2. Use precision-focused retrieval for factual queries.
3. Decompose analytical queries into sub-questions for comprehensive coverage.
4. Seek diverse viewpoints for opinion-based queries.

## Connects To
- Relates to vector search setup from Chapter 1 and query transformations from Chapter 5.