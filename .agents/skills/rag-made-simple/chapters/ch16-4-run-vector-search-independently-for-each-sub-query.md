# Chapter 16: 4. Run vector search independently for each sub-query

## Core Idea
This chapter introduces three query transformation strategies—rewriting, step-back prompting, and sub-query decomposition—to improve retrieval and generation in technical systems.

## Frameworks Introduced
- **Query Rewriting**: Sharpens vague queries to match knowledge bases.
  - When to use: Vague or overly specific questions.
  - How: Modify the query for better alignment with the knowledge base's language.

- **Step-Back Prompting**: Expands specific questions by broadening their context.
  - When to use: Questions requiring foundational context not provided explicitly.
  - How: Expand the search scope by prompting for broader background information.

- **Sub-Query Decomposition**: Splits complex or multi-faceted questions into focused sub-queries.
  - When to use: Complex queries with multiple aspects or requiring background context.
  - How: Break down the query into smaller, more specific sub-queries.

## Key Concepts
- **Vector Search**: A technique for efficient similarity-based retrieval in large document collections.
- **Chunk Collection**: The process of gathering and storing text segments from retrieved documents.
- **Deduplication**: Removing duplicate or overlapping results to enhance retrieval quality.
- **Generation Model**: An AI system used to generate comprehensive answers based on input data.

## Mental Models
- Use Query Rewriting when your user’s question is vague but relevant. For example, if a user asks "What are some applications of machine learning?" rewrite it to "What are the most common and impactful applications of machine learning in modern technology?"
- Think of Step-Back Prompting as broadening the search scope for specific questions. For instance, prompt users to provide context when asking about "How does photosynthesis work?" by suggesting "Explain the process of photosynthesis and its significance in plant growth."
- Use Sub-Query Decomposition when handling complex or multi-faceted questions. For example, decompose a question like "How does the climate change affect global food production?" into sub-queries such as "What are the primary causes of climate change?" and "How do rising temperatures impact agricultural productivity?"

## Anti-patterns
- Avoid isolated vector searches that fail to capture foundational context or multiple facets of a query. For example, avoid searching for "photosynthesis" without considering its broader implications in plant biology.

## Code Examples
```python
def improved_query_handling(query):
    # Step 1: Decompose the original query into sub-queries
    sub_queries = decompose_query(query)
    
    # Step 2: Rewriting each sub-query for specificity
    rewritten_sub_queries = [
        rewrite_query(sub_q) for sub_q in sub_queries
    ]
    
    # Step 3: Run vector search independently for each sub-query
    results = []
    for sub_q in rewritten_sub_queries:
        chunked_results = run_vector_search(sub_q)
        results.extend(chunked_results)
        
    # Step 4: Deduplicate overlapping results
    unique_results = deduplicate(results)
    
    # Step 5: Generate comprehensive answers using the generation model
    answer = generate_answer(query, unique_results)
    
    return answer
```

## Reference Tables

| Technique                | Latency Impact | Complexity Impact | Accuracy Impact |
|--------------------------|-----------------|-------------------|-----------------|
| Query Rewriting          | Moderate        | Low               | Significant      |
| Step-Back Prompting      | Moderate        | Low               | Minimal         |
| Sub-Query Decomposition  | Moderate        | High              | Significant      |

## Key Takeaways
1. Use query rewriting to sharpen vague or overly specific questions.
2. Apply step-back prompting when foundational context is missing from the user’s question.
3. Decompose complex queries into focused sub-queries to cover all aspects of the original question.

## Connects To
- Relates to chunking strategies (Chapter 4) and relevancy grading techniques discussed in Chapter 3.