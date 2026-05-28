# Chapter 32: 1. Preparation: chunk the document

## Core Idea
The chapter introduces a fusion retrieval pipeline that combines vector search ( semantic understanding) and BM25 search (keyword matching) to enhance search accuracy for mixed query types.

## Frameworks Introduced
- **Vector Search**: Built using embeddings, designed for semantic understanding.
  - When to use: For natural language questions requiring meaning-based retrieval.
  - How: Embed each chunk, store in a vector store, and retrieve top-K chunks based on similarity scores.
  
- **BM25 Search**: Built using term statistics, optimized for keyword matching.
  - When to use: For queries needing exact term matches (e.g., product codes).
  - How: Tokenize each chunk, build term frequency-inverse document frequency (TF-IDF) vectors, and retrieve top-K chunks based on keyword match scores.

## Key Concepts
- **Chunking**: The process of splitting the document into manageable units for indexing.
- **Vector Index**: Stores embeddings to support semantic search.
- **BM25 Index**: Uses TF-IDF scoring to find keyword matches efficiently.
- **Score Normalization**: Scales similarity and keyword match scores (e.g., min-max normalization) to a common 0-1 range.

## Mental Models
- Use vector search when the query is a natural language question requiring semantic understanding.  
- Think of BM25 as a tool for finding exact term matches in technical or factual queries.

## Anti-patterns
- **Avoid over-reliance on one method**: Only use BM25 if the query requires exact keyword matches without semantic context.
- **Avoid missing normalization**: Failing to normalize scores can lead to inaccurate merging of results from different search methods.

## Code Examples
```python
# Example code snippet for combining scores with weights

vector_score = model1.get_similarity_score(query, chunk)
bm25_score = model2.get_keyword_score(query, chunk)

normalized_vector = min_max_normalize(vector_score)
normalized_bm25 = min_max_normalize(bm25_score)

final_score = (0.6 * normalized_vector) + (0.4 * normalized_bm25)
```

- **What it demonstrates**: Weighted combination of semantic and keyword search scores to balance their contributions.

## Reference Tables
| Retrieval Method | Blind Spots |
|------------------|-------------|
| Vector Search    | Exact terms, acronyms, proper nouns |
| BM25 Search      | Meaningful context, conceptual queries |

## Key Takeaways
1. Use vector search for semantic understanding in natural language questions.
2. Use BM25 for exact keyword matching in technical or factual queries.
3. Normalize scores to ensure fair comparison between different retrieval methods.
4. Tune weights based on query patterns to balance semantic and keyword signals.

## Connects To
- Relates to Chapter 1: Vector Search
- Relates to Chapter 5: Query Transformations