# Chapter 17: Chapter 8. Semantic Search

## Core Idea
Semantic search enhances traditional search by enabling meaning-based retrieval through dense retrieval, reranking, and RAG systems.

## Frameworks Introduced
- **Dense Retrieval**: Uses embeddings to find similar documents based on query embedding.
  - When to use: When you need a quick semantic search over a large corpus.
  - How: Convert text into numeric representations (embeddings) and retrieve nearest neighbors.

- **Reranking**: Takes initial search results and scores their relevance, reordering them.
  - When to use: After dense retrieval or other initial search steps to refine results.
  - How: Apply reranking models that score document relevance based on query and context.

- **RAG (Retrieval-Augmented Generation)**: Combines LLMs with search capabilities to reduce hallucinations.
  - When to use: To generate factual answers by incorporating relevant information from a dataset.
  - How: Formulate answers using an LLM while citing sources retrieved from the corpus.

## Key Concepts
- **Embeddings**: Numeric representations of text for similarity-based retrieval.
- **Vector Database**: A store of precomputed embeddings for efficient search.
- **Query Embedding**: The process of converting a query into an embedding to find relevant documents.
- **Reranking Model**: A language model that scores and reorders retrieved results based on relevance.
- **Hallucinations**: LLM-generated factual errors, reduced using RAG.
- **RAG System**: Integrates an LLM with search capabilities for generating answers with sources.

## Mental Models
- Use dense retrieval when you need a quick semantic search over a large corpus.
- Think of reranking as refining results after initial retrieval based on query and context.
- Avoid hallucinations by using RAG to ground LLM-generated answers in relevant information.

## Anti-patterns
- **Avoid not using embeddings for search**: This can lead to inefficient or irrelevant results.
- **Avoid ignoring the context in reranking**: Context is crucial for accurate result ordering.

## Code Examples
```python
# Example of setting up dense retrieval with Cohere's VectorStore
from cohere import VectorStore

vector_store = VectorStore(
    documents=documents,
    embedding_model="all-mpnet-base-v2",
    persist_to="file",
    index_name="interstellar_index"
)

query = "What are the key themes of Interstellar?"
results = vector_store.search(query, k=3)
```

This code demonstrates setting up a dense retrieval system using Cohere's VectorStore to search for relevant documents based on query embedding.

## Reference Tables
| Framework          | Steps/Use Case                          |
|--------------------|------------------------------------------|
| Dense Retrieval    | Convert text to embeddings and retrieve similar documents. |
| Reranking          | Take initial results and reorder them based on relevance.  |
| RAG                | Use LLMs with search capabilities for factual answers |

## Key Takeaways
1. Semantic search is essential for improving search accuracy beyond keyword matching.
2. Dense retrieval is ideal for quick, meaning-based searches using embeddings.
3. Reranking refines results by considering query and context.
4. RAG combines LLMs with search to generate factual answers while citing sources.
5. Avoid hallucinations by integrating RAG into your systems.

## Connects To
- Relates to previous chapters on embeddings, vector spaces, and language models.