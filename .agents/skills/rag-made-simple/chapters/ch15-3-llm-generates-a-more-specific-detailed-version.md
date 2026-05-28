# Chapter 15: 3. LLM generates a more specific, detailed version

## Core Idea
This chapter explores strategies to enhance question specificity and retrieval accuracy when using large language models (LLMs) for answering questions through vector search.

## Frameworks Introduced
- **Step-Back Prompting**: A method that generalizes the query to retrieve foundational context before addressing the original question.
  - When to use: When a specific question cannot be answered well without broader context.
  - How: Send the query to an LLM with instructions to generalize, then merge retrieved chunks for comprehensive answers.

## Key Concepts
- **Vector Search**: A method that retrieves documents based on their similarity to a query vector.
- **Step-Back Prompting**: Using generalization to inform specificity in queries.
- **Sub-Query Decomposition**: Breaking complex questions into simpler parts for targeted retrieval.

## Mental Models
- Use Step-Back Prompting when you need foundational context before answering specific questions. Think of it as using a broad question to retrieve general information that informs the answer to your original, more specific query.

## Anti-patterns
- **Over-Specification**: Using queries that are too vague or general for retrieval systems, leading to missed relevant information.

## Code Examples
```
# Example code snippet for Step-Back Prompting
query = "What are the impacts of climate change on the environment?"
generalized_query = prompt_with_generalization(query)
retrieved_chunks = vector_search(generalized_query)
final_answer = generate_answer(original_query, retrieved_chunks)
```

## Reference Tables

| Strategy          | When to Use                          | How Implementation Looks |
|-------------------|---------------------------------------|---------------------------|
| Step-Back Prompting | Broad questions needing context       | Generalize query first    |
| Sub-Query Decomposition | Complex questions requiring multiple aspects | Break into focused sub-queries |

## Key Takeaways
1. Use Step-Back Prompting when your question requires broader context to be answered accurately.
2. Apply Sub-Query Decomposition for complex questions by breaking them into simpler parts.
3. Balance between specificity and generalization to avoid redundancy or inefficiency.

## Connects To
- Relates to query refinement techniques in information retrieval systems.