# Chapter 7: Search Engine Optimization for E-Commerce

## Core Idea
Optimizing an e-commerce search engine requires balancing speed, accuracy, and relevance while addressing challenges like latency, data consistency, and scalability. This chapter outlines architectural strategies, machine learning techniques, and best practices to achieve efficient and effective search results.

---

### Frameworks Introduced

#### 1. **Caching Strategy**
- Uses Least Recently Used (LRU) and Most Recently Used (MRU) policies.
  - When: During peak traffic or slow response times.
  - How: Caches query results for sub-second latency, with MRU evicting older data if memory is full.

#### 2. **Real-Time Search Flow**
- Combines fast path (API gateway) and fallback path (gen AI service).
  - When: For high-volume or complex queries requiring human insight.
  - How: Directs low-latency searches to the fast path, with fallback for ambiguous results via gen AI.

#### 3. **Vector Database for Semantic Search**
- Stores product embeddings for semantic matching.
  - When: For queries that don't match exact keywords but require conceptual understanding.
  - How: Uses machine learning models (e.g., GPT-5o) to generate enriched search prompts and vectorized product data.

#### 4. **Product Discovery Cache**
- Enhances recommendations with complementary products based on user queries.
  - When: For users searching for specific items or categories.
  - How: Analyzes purchase history and co-purchase analytics to suggest related products.

---

### Key Concepts

1. **LRU Caching**: Excludes the least recently used query result after a threshold is reached.
2. **MRU Caching**: Replaces older results with new ones if memory capacity is exceeded.
3. **Vector Embeddings**: Represents products as numerical vectors for semantic search.
4. **Gen AI Service**: Uses large language models (e.g., GPT-5o) for query understanding and refinement.

---

### Mental Models

1. **Use Caching When**:  
   Optimize for sub-second latency during peak traffic or slow response times.

2. **Think of Machine Learning as**:  
   A tool to enhance search accuracy but requiring careful model integration and validation.

3. **Avoid Over-Reliance on ML**:  
   Validate models with historical data and ensure they generalize well beyond training examples.

---

### Anti-Patterns

1. **Stale Data**: Using outdated product or user data for recommendations.
2. **Over-Reliance on Machine Learning**: Ignoring validation steps, leading to unreliable results.
3. **Ignoring Latency Tradeoffs**: Balancing speed and accuracy without considering system bottlenecks.

---

### Code Examples
```python
# Example of semantic search setup using Elasticsearch
from elasticsearch import Elasticsearch

es = Elasticsearch(
    [index="products"],
    {
        "mappings": {
            "dynamic": {"fields": {"product": {"keyword": True}}
        }
    }
)

# Example of vector database query
import faiss
import numpy as np

def product_vector_query(index, product_info):
    # Convert product_info to numpy array
    product_array = np.array(product_info)
    
    # Query the vector index
    results = index.search(
        product_array,
        k=10  # Return top 10 similar products
    )
    
    return results
```

---

### Reference Tables

| Component                | Function                          |
|-------------------------|------------------------------------|
| **Caching Layer**       | Reduces query response time          |
| **Vector Database**      | Facilitates semantic search           |
| **Product Discovery**   | Enhances user recommendations        |

---

### Key Takeaways
1. Optimize for sub-second latency using caching strategies.
2. Leverage machine learning models for enhanced search accuracy.
3. Validate and monitor systems to avoid stale data issues.

This chapter provides actionable insights for building efficient e-commerce search engines, balancing speed, relevance, and user experience.