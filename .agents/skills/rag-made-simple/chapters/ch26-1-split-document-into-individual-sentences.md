# Chapter 26: 1. Split document into individual sentences

## Core Idea
The chapter introduces semantic chunking, a method that splits documents into coherent chunks based on topic boundaries identified through sentence embeddings.

## Frameworks Introduced
- **Embedding Similarity for Breakpoints**:  
  - When to use: For splitting text at natural topic shifts.
  - How: Compute distances between consecutive sentences' embeddings and set thresholds (percentile, standard deviation, or IQR) to identify breakpoints.

## Key Concepts
- **Sentence Embeddings**: Represent each sentence as a dense vector in a continuous space.
- **Distance Thresholds**: Determine when text boundaries shift by measuring embedding distances.
- **Semantic Chunking**: Groups sentences into internally coherent chunks based on topic consistency.

## Mental Models
- Use semantic chunking when you need to split documents at natural topic shifts. Think of it as identifying breakpoints where the meaning changes significantly.

## Anti-patterns
- **Avoid fixed-size and proposition-based chunking**: Fixed chunks blend unrelated topics, while proposition decomposition is costly and less suitable for most applications.

## Code Examples
```python
# Example code snippet to compute sentence distances using embeddings
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')
sentences = ["Sentence 1.", "Sentence 2."]
embeddings = model.encode(sentences)
distances = [cosine_distance(embeddings[i], embeddings[i+1]) for i in range(len(sentences)-1)]

# Set threshold using percentile
threshold = np.percentile(distances, 90)

# Split sentences at distances exceeding the threshold
chunks = []
current_chunk = [sentences[0]]
for i in range(1, len(sentences)):
    if distances[i-1] > threshold:
        chunks.append(current_chunk)
        current_chunk = [sentences[i]]
    else:
        current_chunk.append(sentences[i])
chunks.append(current_chunk)

print("Semantic chunks:", chunks)
```

This code demonstrates how to compute cosine distances between consecutive sentence embeddings and split them based on a percentile-based threshold.

## Reference Tables
| Chunking Strategy          | Preparation Cost      | Query Latency  | Chunk Quality   | Chunk Size       |
|----------------------------|-----------------------|-----------------|------------------|--------------------|
| Fixed-size chunking        | Moderate              | Same as RAG     | Low quality      | Predictable       |
| Window-based chunking      | No LLM calls          | Same as RAG     | High quality     | Fixed size         |
| Semantic chunking         | One embedding per sentence | Same as RAG  | High quality     | Variable           |
| Proposition decomposition   | Expensive             | Same as RAG     | Highest quality  | Smallest units    |

## Key Takeaways
1. Use semantic chunking when you need topic-boundary-aware text splits without LLM costs.
2. It balances preparation cost and retrieval precision, offering variable-length chunks that capture single topics.
3. Semantic chunking is ideal for long documents with clear topic transitions but less so for short or consistent-topics documents.

## Connects To
- Relates to fixed-size chunking (Chapter 1) and proposition decomposition (Chapter 4).
- Builds on context enrichment window concepts from Chapter 8 while offering better retrieval precision.