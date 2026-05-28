# Chapter 9: Semantic Search Using Bi-Encoder and FAISS

## Core Idea
This chapter teaches how to implement semantic search using Bi-Encoder models and FAISS for efficient similarity search. It demonstrates the process of encoding queries and documents into dense vectors, leveraging cosine similarity to find similar items.

## Frameworks Introduced
- **Bi-Encoder**: 
  - When to use: For large-scale document collections where efficiency is crucial.
  - How: Uses two encoder models (query and candidate) for pre-computing document embeddings, enabling fast retrieval during search.

## Key Concepts
- **Cosine Similarity**: A similarity metric that measures the cosine of the angle between two vectors.
- **Cross-Encoder**: A model used to generate query embeddings but not typically preferred for large-scale datasets.
- **BER T Model**: An encoder model used to convert text into dense vector representations.
- **FAISS**: A library designed for efficient similarity search and clustering of dense vectors, offering optimized indexing techniques.

## Mental Models
- Use Bi-Encoder when dealing with large-scale documents. Think of Bi-Encoder as a tool that efficiently handles the pre-computation of document embeddings to enable fast retrieval during search.

## Anti-patterns
- **Not indexing embeddings for efficient search**: This can lead to inefficient results due to the lack of precomputed vectors.
- **Not normalizing query vectors**: Failing to normalize query vectors can result in inaccurate similarity measurements.

## Code Examples
```python
import numpy as np
import scipy.spatial
from sentence_transformers import SentenceTransformer

def cosine_search(query_embedding, review_embeddings, k):
    query_embedding = query_embedding.reshape(-1)  # Ensure correct shape
    dot_products = np.dot(review_embeddings, query_embedding)
    query_norm = np.linalg.norm(query_embedding)
    review_norms = np.linalg.norm(review_embeddings, axis=1)
    cosines = dot_products / (query_norm * review_norms)
    top_indices = np.argpartition(cosines, -k)[-k:]  # Use partitioning for efficiency
    top_cosine_similarities = cosines[top_indices]
    return top_indices, top_cosine_similarities

# Example usage:
# query_embedding = model.encode([query]).reshape(-1)
# k = 5
# indices, distances = cosine_search(query_embedding, review_embeddings, k)
```

## Reference Tables
| Parameter | Value/Definition |
|-----------|-------------------|
| BER T Model Architecture | BERT-base-uncased (RoBERTa-based) |
| Bi-Encoder Components | Query encoder: BER T; Candidate encoder: BER T |
| FAISS Indexing Technique | Flat index with cosine similarity |

## Key Takeaways
1. Use Cosine Similarity for semantic search to measure the similarity between query and document embeddings.
2. Leverage Bi-Encoder models for efficient retrieval of large-scale document collections.
3. Implement FAISS indexing to enable fast and scalable similarity search.
4. Evaluate search results based on distance scores to ensure relevance.

## Connects To
- Vector space models (Chapter 3)
- Information retrieval techniques