# Chapter 21: 3. For each chunk, prepend the title to the chunk text

## Core Idea
Prepend document titles to chunks to preserve context during retrieval, enhancing accuracy especially in multi-source knowledge bases.

## Frameworks Introduced
- **Reranking with Context**: 
  - When to use: When retrieving topically relevant but contextually incorrect chunks.
  - How: Pass augmented chunks through a reranker to refine results.

## Key Concepts
- **Richer Headers**: Include document titles, summaries, and section hierarchies for improved retrieval accuracy.
- **Relevance Score**: A document title can boost relevance from 0.1 to 0.9 when prepended to a chunk.
- **Meaning Space Visualization**: Contextual headers shift embeddings into specific topic neighborhoods.

## Mental Models
Use header augmentation when you need context preservation, especially in multi-source knowledge bases with pronouns and implicit references.

## Anti-patterns
Avoid prepending titles when:
- Retrieval accuracy doesn't benefit (single or distinct documents).
- Chunks are self-contained without pronouns.

## Code Examples
```python
# Example code snippet for prepending document title to a chunk
augmented_chunk = f"{document_title}\n{chunk_text}"
```
- **What it demonstrates**: Improves retrieval accuracy by preserving context in multi-source knowledge bases.

## Reference Tables

| Parameter              | Impact on Retrieval Accuracy |
|------------------------|------------------------------|
| Number of documents    | High (multiple overlapping topics) |
| Context density       | Low (chunks with pronouns and references) |

## Key Takeaways
1. Prepend document titles to chunks to preserve context during retrieval.
2. Use richer headers for multi-source knowledge bases where context is critical.
3. Avoid header augmentation when it doesn't improve accuracy or with self-contained chunks.

## Connects To
- Relates to reranking techniques (Chapter 5) and vector store operations (Chapter 6).