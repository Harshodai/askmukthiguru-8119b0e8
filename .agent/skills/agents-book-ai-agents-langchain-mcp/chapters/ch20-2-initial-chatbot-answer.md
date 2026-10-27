# Chapter 20: 2. Initial chatbot answer

## Core Idea
This chapter introduces Retrieval-Augmented Generation (RAG), a design pattern that enhances chatbots by integrating vector stores for efficient information retrieval and generation.

## Frameworks Introduced
- **ChromaDB**: A vector store optimized for semantic search, enabling efficient similarity searches in high-dimensional spaces.
  - When to use: Ideal for scenarios where large document collections or diverse data sources are involved.
  - How: Indexes text chunks into embeddings, which are stored in a vector database for quick retrieval.

## Key Concepts
- **Vector Store**: A database storing text chunks and their embeddings, facilitating efficient semantic searches.
- **Document Embeddings**: Numerical representations of text used to measure similarity between documents.
- **Similarity Search**: Retrieving relevant document chunks based on query embeddings.
- **Query Generation**: Feeding retrieved content into an LLM to synthesize answers.

## Mental Models
- Use RAG when you need to augment chatbot responses with context from external data sources. Think of it as enhancing the basic Q&A process by integrating semantic search and generation.

## Anti-patterns
- **Hallucinations**: Avoid relying solely on LLMs without providing relevant context, which can lead to incorrect or nonsensical answers.
- **Inefficient Indexing**: Do not index raw text; instead, preprocess chunks into embeddings for better search performance.

## Code Examples
```python
from ChromaDB import Collection

# Initialize a vector store with ChromaDB
store = Collection("my-vector-store")

# Add documents to the store
store.add(
    documents=["text chunk 1", "text chunk 2", ...],
    metadatas=[{"source": "source1"}, {"source": "source2"}, ...],
)

# Query the vector store for similar documents
results = store.similarity_search("query question", k=3)
```

This demonstrates how to set up and query a vector store using ChromaDB.

## Reference Tables
| Framework      | Purpose                                      |
|----------------|-----------------------------------------------|
| Vector Store   | Efficiently stores and retrieves text chunks  |
| Document Embeddings  | Converts text into numerical vectors           |
| Similarity Search | Finds relevant document chunks                |
| Query Generation | Synthesizes answers using LLM               |

## Key Takeaways
1. RAG combines retrieval from external data sources with generation to improve chatbot responses.
2. Vector stores are essential for efficient semantic search, reducing reliance on large text inputs.
3. Proper indexing and embedding preprocessing are crucial for effective information retrieval.

## Connects To
- Earlier chapters on LLM fundamentals and semantic search provide foundational knowledge for this chapter's concepts.