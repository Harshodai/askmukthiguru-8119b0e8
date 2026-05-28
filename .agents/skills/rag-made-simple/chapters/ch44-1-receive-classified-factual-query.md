# Chapter 44: 1. Receive classified factual query

## Core Idea  
The chapter introduces adaptive retrieval strategies for handling classified factual queries by tailoring the search process based on analytical needs.

## Frameworks Introduced  
- **Enhanced Query**: A technique that decomposes an analytical question into focused sub-queries to retrieve diverse and relevant documents.
  - When to use: When the query spans multiple subtopics requiring broad coverage.
  - How: Decompose the query, run separate retrievals for each sub-query, and select a diverse subset from the combined pool.

- **Diversity Through Viewpoint Identification**: A strategy that identifies distinct viewpoints on a topic to ensure balanced retrieval of perspectives.
  - When to use: When the knowledge base contains imbalanced viewpoints (e.g., ten supporting one perspective vs. two others).
  - How: Use an LLM to identify viewpoints, run separate retrievals for each, and select documents representing the broadest range of opinions.

- **Personalization Through Context Incorporation**: A method that incorporates user context into the query to retrieve contextually relevant documents.
  - When to use: When the query depends on external information not included in the original question (e.g., budget constraints).
  - How: Merge user context with the query, run over-retrieval against a vector store, and rank candidates based on both relevance and alignment with the user’s specific situation.

## Key Concepts  
- **Breadth Through Decomposition**: Retrieving multiple focused sub-query results to cover diverse aspects of a topic.  
- **Diversity Through Viewpoint Identification**: Ensuring retrieval represents different viewpoints or perspectives.  
- **Contextual Strategy**: Incorporating external context into the query to refine retrieval outcomes.

## Mental Models  
- Use enhanced query when you need breadth across multiple subtopics.  
- Think of diversity through viewpoint identification as ensuring balanced representation of perspectives.  
- Personalize retrieval by incorporating user context into the search process.

## Anti-patterns  
- **Avoid treating every question the same**: This leads to imbalanced or redundant retrieval results, failing to capture diverse viewpoints or contextual nuances.

## Code Examples  
```python
# Example code for enhanced query implementation
from langchain.schema import Document

def retrieve_passages(query: str, vector_store):
    # Decompose query into sub-queries
    sub_queries = decompose_query(query)
    
    # Run separate retrievals for each sub-query
    candidate_pools = []
    for sub_query in sub_queries:
        retrieved = vector_store.similarity_search(sub_query, k=2000)
        candidate_pools.append(retrieved)
    
    # Combine and select top K candidates with diversity
    combined = sum(candidate_pools, [])
    scores = [(doc.page_content, doc.metadata.get('score', 1)) for doc in combined]
    sorted_scores = sorted(scores, key=lambda x: (-x[1], x[0]))
    top_k = [doc[0] for doc in sorted_scores[:K]]
    
    return top_k
```

This code demonstrates over-retrieval and scoring to ensure diversity and relevance.

## Reference Tables  

| Strategy                | When to Use                          | How Implementation Works                     |
|-------------------------|---------------------------------------|----------------------------------------------|
| Enhanced Query          | Broad coverage across multiple topics  | Decompose query into focused sub-queries       |
| Diversity Through Viewpoint | Imbalanced viewpoints                 | Identify and retrieve documents for each viewpoint   |
| Personalization Context | User-specific context                  | Merge user context with query, rank by relevance and alignment |

## Key Takeaways  
1. Use enhanced queries when you need to cover multiple aspects of a topic.  
2. Incorporate diversity through viewpoint identification to ensure balanced retrieval.  
3. Apply contextual strategies by merging external context into the query for tailored results.

## Connects To  
- Relates to information retrieval techniques and AI-driven search systems that prioritize breadth, balance, and personalization.