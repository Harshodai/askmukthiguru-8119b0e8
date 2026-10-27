# Chapter 20: Dense Retrieval and Reranking with RAG

## Core Idea
Improving search systems by combining dense retrieval (using text embeddings) with reranking techniques to enhance result relevance.

## Frameworks Introduced
- **Dense Retrieval**: Embed query and documents into vector space, retrieve top candidates using similarity metrics like cosine similarity.
  - When to use: When you need precise, context-aware search results for dense text data.
  - How: Convert query and documents to embeddings, compute similarity scores, sort by descending score.

- **Reranking (mono-BERT)**: Train an LLM to rank retrieved documents based on their relevance to the query.
  - When to use: When you need fine-tuned relevance scores for a small set of results.
  - How: Use rerankers like mono-BERT to assign scores and reorder results.

## Key Concepts
- **Embeddings**: Numerical representations of text that capture semantic meaning (e.g., using BERT).
- **Cosine Similarity**: Measure similarity between vectors by their dot product divided by their magnitudes.
- **mono-BERT Reranker**: Fine-tuned LLM trained to predict relevance scores for ranked documents.

## Mental Models
- Use dense retrieval when you need precise, context-aware search results for dense text data.
  - Example: Search for movie reviews with high box office success.
  
- Use rerankers like mono-BERT when you need fine-tuned relevance scores for a small set of results.
  - Example: Refining the top 10 results from dense retrieval.

## Anti-patterns
- **Over-reliance on dense methods**: Can fail if combined with irrelevant or sparse data sources.
  - Solution: Always combine dense retrieval with complementary approaches like hybrid search.

## Code Examples
```python
# Reranking example using Co reranking
reranker = co.reranker.Reranker(
    retriever=retailer,
    documents=docs,
    top_k=10,
    num_candidates=208,
    return_documents=True
)
results = reranker([query, query], ["BM25", "BM25"], top_n=3, 
                   return_documents=True)

# Print results with relevance scores
for hit in results.hits:
    print(f"Relevance score: {hit['score']:.4f}\n"
          f"Text: {text.replace('\n', ' ')}\n")
```

## Reference Tables
| **Search System**       | **Key Features**                                                                 |
|--------------------------|-----------------------------------------------------------------------------|
| Hybrid Retrieval         | Combines dense and BM25 for better performance on structured and sparse data.  |
| Dense Retrieval          | Uses embeddings and cosine similarity for precise, context-aware search.    |
| Reranking (mono-BERT)   | Fine-tunes relevance scores for small result sets.                           |

## Key Takeaways
1. Use dense retrieval when you need precise, context-aware search results.
2. Implement rerankers like mono-BERT to refine the relevance of your search results.
3. Evaluate search systems using metrics like mean average precision (MAP) and normalized discounted cumulative gain (nDCG).

## Connects To
- Understanding how embeddings work for semantic search.
- Learning about language models and their application in text analysis.