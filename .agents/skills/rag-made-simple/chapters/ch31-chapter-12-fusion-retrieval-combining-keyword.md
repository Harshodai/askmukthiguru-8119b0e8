# Chapter 31: Chapter 12: Fusion Retrieval: Combining Keyword and Semantic Search

## Core Idea
Fusion retrieval combines vector-based (semantic) and keyword-based (exact term) search to avoid their individual blind spots, ensuring no relevant results are missed.

## Frameworks Introduced
- **BM25 Index**: A keyword-matching algorithm that scores chunks based on term frequency, inverse document frequency, and length normalization.
  - When to use: When exact matches or specific terminology is crucial.
  - How: Tokenizes queries into words, calculates scores for each chunk based on matching terms.

## Key Concepts
- **Semantic Search Blind Spot**: Semantic search misses exact terms relevant to the query.
- **Keyword Search Blind Spot**: Keyword search misses semantically relevant but word-mismatched results.

## Mental Models
- Use Fusion Retrieval when you need both semantic understanding and exact term matching in your knowledge base queries. Think of it as combining semantic and keyword searches for a balanced approach.

## Anti-patterns
- Avoid using only one type of retrieval (either BM25 or vector search) without combining, as it risks missing relevant results due to each method's blind spots.

## Code Examples
```python
# Example BM25 Scoring Calculation

def bm25_score(query_terms, chunk):
    # Term Frequency: Number of times a query term appears in the chunk
    term_freq = count_of_term_in_chunk(term)
    
    # Inverse Document Frequency: Logarithm of total documents divided by document frequency of the term
    idf = log(total_documents / doc_frequency(term))
    
    # Length Normalization: Reduces score for longer chunks
    length_factor = 1.0 / (1 + len(chunk))
    
    # Calculate raw score components
    raw_score = (term_freq * idf) * length_factor
    
    return raw_score

# Demonstrate how BM25 scores a chunk based on query terms, term frequency, and normalization factors.
```

This code snippet demonstrates the calculation of a BM25 score by considering term frequency, inverse document frequency, and length normalization.

## Reference Tables
| Parameter | Description |
|---|---|
| BM25 Term Frequency | Number of times a query word appears in the chunk. |
| Inverse Document Frequency (IDF) | Logarithm of total documents divided by the number of documents containing the term. |
| Length Normalization Factor | Reduces score for longer chunks, calculated as 1 / (1 + length). |

## Key Takeaways
1. Use Fusion Retrieval when you need both exact terms and semantic meaning in your search results.
2. Combine vector-based and keyword-based searches to avoid each method's blind spots.
3. Normalize BM25 scores by scaling them between 0 and 1 for consistent comparison with vector similarity scores.

## Connects To
- Relates to Chapter 1: Embeddings, Vector Search, and the Basic RAG Pipeline, as it builds on semantic search concepts while introducing exact term matching.