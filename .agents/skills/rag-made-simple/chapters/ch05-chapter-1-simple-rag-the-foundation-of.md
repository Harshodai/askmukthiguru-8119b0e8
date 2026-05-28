# Chapter 5: Simple RAG: The Foundation of Document-Powered AI

## Core Idea  
RAG (Retrieval-Augmented Generation) enhances knowledge work by integrating retrieval steps into language models to answer questions based on document context.

## Frameworks Introduced  
- **RAG**: A framework that combines retrieval and generation for improved knowledge work.  
  - When to use: When dealing with structured or semi-structured documents requiring accurate, context-based answers.  
  - How: Augment a language model with a retrieval step before generating responses, using precomputed document embeddings.

## Key Concepts  
- **Embeddings**: Mathematical representations of text that capture semantic meaning for similarity search.  
- **Vector Database**: A database optimized for efficient similarity searches, such as FAISS.  
- **Document Preparation Pipeline**: A multi-step process to prepare documents for RAG, including extraction, chunking, cleaning, and embedding generation.

## Mental Models  
Use RAG when you need a language model to answer questions based on external document context rather than relying solely on memory or guessing.

## Anti-patterns  
- **Without RAG**: Language models answering from memory, leading to hallucinations and unreliable responses. This occurs when retrieval steps are omitted during the preparation phase.

## Code Examples  
```python
# Example code snippet for embedding generation using FAISS
import faiss

# Load precomputed document embeddings into a FAISS index
index = faiss.read_index("path/to/embeddings")
index.add(doc_embeddings)

# Query the index to find relevant documents
results = index.search(query_embedding, k=3)
```

- **What it demonstrates**: Efficient retrieval and generation pipeline using vector databases for context-based answering.

## Reference Tables  
| Parameter | Description | Value/Setting |
|---|---|---|
| Chunk Size | Size of each text chunk | 1,000 characters |
| Overlap | Number of lines between chunks | 200 |
| Cleaning | Text normalization steps | Format artifacts removal |
| Embedding Model | Type of embedding used | Pre-trained models like BERT |
| Vector Database | Search engine for embeddings | FAISS or similar |

## Key Takeaways  
1. RAG improves AI's ability to answer questions based on structured document context.  
2. Proper document preparation is critical for effective RAG implementation, including chunking and embedding generation.  
3. Retrieval steps are essential to minimize hallucinations and improve answer accuracy.

## Connects To  
- Relates to knowledge graphs as a broader approach to document-powered AI.  
- Connects with the concept of open-book exams in education, where models benefit from external context.