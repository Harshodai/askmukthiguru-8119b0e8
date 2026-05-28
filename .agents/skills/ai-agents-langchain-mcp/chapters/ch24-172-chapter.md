# Chapter 25: Advanced Indexing

## Core Idea
Advanced indexing techniques enhance retrieval accuracy by leveraging multiple embeddings for each text chunk, improving searchability in vector stores.

## Frameworks Introduced
- **Multiple Embeddings per Chunk**:  
  - When to use: When dealing with complex or semi-structured data.  
  - How: Calculate multiple embeddings (e.g., sentence-transformers) for each chunk to capture diverse contextual information.

## Key Concepts
- **Vector Store**: A database storing high-dimensional vectors representing text chunks.
- **Embeddings**: Mathematical representations of text that enable semantic searches.

## Mental Models
- Use multiple embeddings when working with complex data sources.  
  - Think of it as enhancing searchability by capturing more context.

## Anti-patterns
- **Relying solely on basic embeddings without optimization**: This can lead to inaccurate or incomplete retrieval results due to insufficient contextual representation.

## Code Examples
```python
from langchain.vectorstores import FAISS
from sentence_transformers import SentenceTransformer

# Calculate multiple embeddings for each chunk
embedder = SentenceTransformer('all-MiniLM-L6-v2')
chunks = ["Chunk 1", "Chunk 2"]
embeddings = embedder.encode(chunks)

# Store embeddings in a vector database
vectorstore = FAISS.from_documents(chunks, embeddings)
```

## Reference Tables

| Data Type        | Appropriate Indexing Strategy          |
|------------------|---------------------------------------|
| Semi-structured  | Use multiple embeddings and fine-grained chunking         |
| Multimodal       | Leverage cross-modal embeddings           |

## Key Takeaways
1. Use multiple embeddings for each text chunk to improve retrieval precision.
2. Optimize chunk splitting strategies for granular context expansion.
3. Indexing should be tailored to the data type, using advanced techniques for complex content.

## Connects To
- Relates to Chapter 7's RAG architecture fundamentals and Chapter 9's metadata integration.