# Chapter 6: 1. Load document and extract raw text

## Core Idea
This chapter teaches how to prepare a knowledge base for answering questions using Retrieval-Augmented Generation (RAG). It outlines the process of splitting documents into chunks, converting them into embeddings, storing vectors in a vector store, and using this system to answer queries by embedding the question and retrieving relevant chunks.

## Frameworks Introduced
- **Simple RAG**: A foundational approach for building an agent skill that combines retrieval and generation.
  - When to use: Ideal for factual questions about single documents or small collections.
  - How: Split text into ~1000-character chunks with ~200-character overlap, convert each chunk into embeddings, store vectors in a vector store, embed queries, retrieve nearest chunks, and generate answers.

## Key Concepts
- **Vector Store**: A database storing numerical representations of text chunks for fast similarity search.
- **Embedding Vector**: A numerical representation of text that captures its meaning for comparison with other texts.
- **Nearest Neighbors**: The most similar text chunks retrieved from a vector store based on embedding proximity.

## Mental Models
- Use Simple RAG when you need to answer factual questions about single documents or small collections. Think of it as combining retrieval and generation into one system.

## Anti-patterns
- **Overly Fixed Chunking**: Avoid using fixed chunk sizes that are too small or too large, as they limit the ability to retrieve relevant information for complex queries.

## Code Examples
```python
# Example code snippet for vector similarity search
from sentence_transformers import SentenceTransformer

# Load and preprocess text chunks (not shown here)
chunks = ["Chunk 1", "Chunk 2", ...]

# Convert text into embeddings
model = SentenceTransformer('all-MiniLM-L6-v2')
chunk_embeddings = model.encode(chunks)

# Store embeddings in a vector store (e.g., FAISS)
vector_store = VectorStoreIndexer(embeddings=chunk_embeddings, documents=chunks)

# Query processing
query = "What is the main cause of climate change?"
query_embedding = model.encode(query)
nearest_chunks = vector_store.similarity_search(query_embedding, k=3)

# Generate answer using language model (not shown here)
```

- **What it demonstrates**: Combining chunking, embedding, and vector search to retrieve relevant information for generating an answer.

## Reference Tables
| Parameter | Decision |
|---|---|
| Chunk Size | 1000 characters with 200 overlap |
| Overlap | High (to preserve context) |

## Key Takeaways
1. Use Simple RAG when answering factual questions about single documents or small collections.
2. Split text into balanced medium-sized chunks for effective retrieval.
3. Understand that query transformation is critical for meaningful similarity search.

## Connects To
- Relates to information retrieval, document preprocessing, and language model integration in AI systems.