# Chapter 18: 1. Receive user question

## Core Idea
The chapter introduces a method called Hypothetical Document Embedding (HyDE) that enhances document retrieval by generating a hypothetical answer from the query, embedding it, and using it to find relevant real documents.

## Frameworks Introduced
- **Hypothetical Document Embedding (HyDE)**: 
  - When to use: When seeking to retrieve documents related to a topic where existing knowledge is insufficient.
  - How: Generate a hypothetical document from the query, embed it, and search for similar real documents.

## Key Concepts
- **Chunk Size Matching**: Ensure the hypothetical document's length matches the actual chunks' size for structural alignment in embedding space.

## Mental Models
- Use Hypothetical Document Embedding when you need to bridge the gap between a query and relevant content that isn't directly available.
  - Think of HyDE as a method to generate contextually similar documents to improve retrieval accuracy.

## Anti-patterns
- **Avoid hallucinations**: If the language model generates incorrect facts, it may retrieve wrong chunks. This is most likely when the model lacks domain knowledge about the topic.

## Code Examples
```python
# Example of adjusting prompt length based on chunk size
chunk_size = 500  # Define desired chunk size in words
prompt_length = "Make the hypothetical document approximately the same size as the chunks in your knowledge base."
```

## Reference Tables

| Chunk Size | Hypothetical Document Length Suggestion |
|------------|----------------------------------------|
| Small (e.g., 100 words) | Short (e.g., 50-75 words)              |
| Medium (e.g., 500 words) | Moderate (e.g., 250-350 words)         |
| Large (e.g., 1000 words) | Long (e.g., 500-800 words)             |

## Key Takeaways
1. Use Hypothetical Document Embedding to improve retrieval accuracy by leveraging embedding space structure.
2. Match the hypothetical document's length to real chunks for optimal alignment in embedding space.
3. Avoid using hallucinations to ensure accurate retrieval.

This chapter connects to broader concepts in AI safety and information retrieval techniques, emphasizing the importance of structured thinking and careful implementation when applying such methods.