# Chapter 27: Contextual Compression: Extracting

## Core Idea
Contextual compression refines retrieval results by extracting only the sentences directly addressing the query, eliminating irrelevant context to improve answer quality.

## Frameworks Introduced
- **Contextual Compression**: A method that extracts relevant portions from retrieved chunks using an LLM.
  - When to use: After retrieval when context needs to be narrowed down for precise answers.
  - How: Feed each chunk and query to the LLM, which returns only sentences addressing the question.

## Key Concepts
- **Chunking**: The process of dividing documents into manageable units.
- **Compression Funnel**: A system where chunks are processed to extract relevant content.
- **Golden Panning Analogy**: A metaphor for refining search results by removing irrelevant material.

## Mental Models
- Use Contextual Compression when you need precise answers from retrieved data. Think of it as a tool that zeroes in on the exact information needed.

## Anti-patterns
- **Not Compressing Enough**: Failing to extract relevant sentences can lead to diluted answers with too much tangential information.

## Code Examples
```python
# Example code snippet demonstrating compression step
def compress_chunk(chunk, query):
    """Extracts only the portions of a chunk that directly address the query."""
    model = LLM()
    result = model.extract_relevant_sentences(chunk, query)
    return result

# Usage
compressed_excerpts = [compress_chunk(chunk, query) for chunk in retrieved_chunks]
```

This code demonstrates how an LLM is used to extract only relevant sentences from each chunk.

## Reference Tables
| Parameter | Description |
|-----------|-------------|
| `query`   | The user's question or prompt. |
| `chunk`   | A pre-retrieved document chunk. |
| `compressed_excerpts` | The refined output containing only query-relevant sentences. |

## Key Takeaways
1. Contextual compression improves answer quality by narrowing context to relevant information.
2. It operates at a finer granularity than relevancy grading, extracting specific sentences instead of filtering chunks.
3. Using this method ensures that the generation model receives focused data for better responses.

## Connects To
- Relates to Chapter 1's RAG pipeline as it enhances retrieval and compression steps.
- Connects to Chapter 3's relevance grading by refining how context is evaluated.
- Builds upon future chapters on improved answer quality using compressed contexts.