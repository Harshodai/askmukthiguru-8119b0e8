# Chapter 21: Retrieval-Augmented Generation (RAG)

## Core Idea
This chapter introduces Retrieval-Augmented Generation (RAG), a technique that combines text retrieval with large language models (LLMs) to provide more accurate answers by leveraging external knowledge. It explains how RAG transforms user questions into embeddings, retrieves relevant chunks from vector stores, and uses LLMs to synthesize responses.

## Frameworks Introduced
- **Vector Stores**: Tools like FAISS, Milvus, Qdrant, and ChromaDB are used for storing and searching text embeddings.
  - When to use: For scenarios requiring efficient semantic search and retrieval of large text datasets.
  - How: Vector stores transform text into dense vectors, enabling similarity searches based on semantic meaning.

## Key Concepts
- **Embeddings**: Numerical representations of text that capture its meaning, used for semantic search.
- **Vector Distance Calculations**: Methods like Euclidean, Cosine, and Hamming distances measure similarity between embeddings.
- **Vector Database**: A database optimized for storing and searching vectors, supporting CRUD operations.

## Mental Models
- Use vector stores when you need to perform semantic searches on large text datasets.
  - Think of vector stores as tools that convert text into a form (embeddings) that can be queried efficiently.

## Anti-patterns
- **Not using vector stores**: Avoid manually searching through documents without leveraging structured embedding storage.
- **Handling outdated data**: Do not use vector stores for real-time data where updates are frequent.
- **Querying during ingestion**: Avoid querying vector databases while importing new data, as it can affect performance and scalability.

## Code Examples
```python
# Example code snippet using ChromaDB in a Jupyter notebook

from chromadb import Client

# Initialize an in-memory client
client = chromadb.Client()

# Create a collection to store text and their related embeddings
tourism_collection = client.create_collection(
    name="tourism_collection"
)

# Insert text chunks with metadata
tourism_collection.add(
    documents=["Paestum, Greek Poseidonia, …[shortened] … Greek temples."],
    metadatas=[{"source": "https://www.britannica.com/place/Paestum"}],
    ids=["paestum-br-01"]
)

# Query the vector store
results = tourism_collection.query(
    query_texts=["How many Doric temples are in Paestum"],
    n_results=1
)

print(results)
```
This demonstrates how to set up and use ChromaDB for semantic search.

## Reference Tables

| Vector Store Type      | Key Features                                                                 |
|------------------------|-----------------------------------------------------------------------------|
| FAISS                  | Lightweight library with immutable data structures, efficient for memory storage. |
| Milvus                 | Supports dense vectors (e.g., TF-IDF) and scalable for large-scale applications. |
| Qdrant                  | Open-source vector store optimized for similarity searches in high-dimensional spaces. |
| ChromaDB               | Enhanced with caching, sharding, and partitioning for improved performance. |

## Key Takeaways
1. RAG combines text retrieval with LLMs to enhance generation by leveraging external knowledge.
2. Vector stores are essential for efficient semantic search and storing metadata alongside text.
3. Use ChromaDB for its scalability, performance optimizations, and support for CRUD operations.

## Connects To
- **Chapter 6**: Discusses vector stores in detail, providing foundational knowledge for this chapter.
- **Chapter 12**: Explores advanced techniques in RAG, building on the concepts introduced here.