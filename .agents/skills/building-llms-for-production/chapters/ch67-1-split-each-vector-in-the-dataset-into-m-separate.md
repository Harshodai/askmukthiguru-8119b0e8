# Chapter 67: Product Quantization for Efficient Vector Search  

## Core Idea  
Product Quantization reduces high-dimensional vector datasets into compact codes by clustering sub-vectors, enabling efficient nearest neighbor search with minimal memory usage.

## Frameworks Introduced  
- **Product Quantization**: A technique that splits vectors into sub-vectors, clusters each using k-means, and replaces them with centroid indices.  
  - When to use: For high-dimensional data requiring fast similarity searches.  
  - How: Split vectors into m sub-vectors, cluster each with k centroids, replace sub-vectors with centroid indices.  

## Key Concepts  
- **Centroid Indexing**: Each vector is represented by the index of its closest centroid in a codebook.  
- **Memory Efficiency**: Reduces storage by replacing high-dimensional vectors with low-dimensional codes.  

## Mental Models  
Use centroid indexing when you need to perform fast nearest neighbor searches on large-scale, high-dimensional datasets. Think of Product Quantization as a way to compress vectors while preserving their ability to find similar items efficiently.

## Anti-patterns  
- **Overfitting**: Using too many centroids can improve accuracy but may not reduce memory usage significantly.  

## Code Examples  
```python
from sklearn.cluster import KMeans
import numpy as np

# Given array of high-dimensional vectors
array = np.array([[8.2, 10.3, 290.1, 278.1, 310.3, 299.9, 308.7, 289.7, 300.1],
                  [0.1, 7.3, 8.9, 9.7, 6.9, 9.55, 8.1, 8.5, 8.99]])

# Split each vector into m=3 sub-vectors
m, k = 3, 2
subvectors = array.reshape(-1, m)

# Perform k-means clustering on each sub-vector
kmeans = KMeans(n_clusters=k, random_state=0).fit(subvectors)
labels = kmeans.labels_.reshape(array.shape[0], -1)

print("Quantized Array:")
print(labels)
```

## Reference Tables  

| Parameter | Value | Description |
|-----------|-------|-------------|
| Number of sub-vectors (m) | 3 | Each vector is split into 3 disjoint sub-vectors. |
| Number of centroids (k) | 2 | Each sub-vector cluster has 2 centroids. |

## Key Takeaways  
1. Use Product Quantization to reduce high-dimensional vectors into compact codes for efficient similarity search.  
2. Split vectors into m sub-vectors and cluster each with k centroids, replacing sub-vectors with centroid indices.  
3. Balance between accuracy and memory usage by carefully choosing the number of centroids (k) and sub-vectors (m).  

## Connects To  
- Relates to vector similarity search techniques in machine learning.