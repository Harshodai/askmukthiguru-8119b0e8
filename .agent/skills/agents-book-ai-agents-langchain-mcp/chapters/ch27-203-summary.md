# Chapter 27: Advanced Indexing and Question Transformation Techniques

## Core Idea
This chapter explores advanced indexing strategies and question transformation techniques to enhance Retrieval-Augmented Generation (RAG) systems, focusing on improving retrieval accuracy, context preservation, and query optimization.

## Frameworks Introduced
- **Multi-vector Indexing**: Uses multiple embeddings per document for better search precision.
  - When to use: For high-dimensional data requiring precise retrieval.
  - How: Embeds each chunk in multiple ways to capture different aspects of the content.
  
- **Parent-Child Indexing**: Stores small chunks as leaves and larger parent chunks for context.
  - When to use: To balance search granularity with contextual relevance.
  - How: Child chunks reference their parent documents, allowing retrieval at varying levels of detail.

## Key Concepts
- **Chunking Strategies**: 
  - Size-based splitting (e.g., by character count or sentences) for content without explicit structure.
  - Structure-based splitting (e.g., using headers in Markdown or book chapters).
  
- **Context Expansion**: Retrieves adjacent chunks to maintain context during retrieval.
  - When to use: To ensure continuity and relevance in multi-document responses.

## Mental Models
- Use Multi-vector Indexing when dealing with complex, high-dimensional data that requires precise retrieval. Think of it as embedding content from multiple perspectives to capture nuances.

## Anti-patterns
- **Over-reliance on Sparse Retrieval**: Avoid using only dense embeddings without considering sparse methods for improved efficiency and accuracy.

## Code Examples
```python
# Example code snippet for parent-child indexing
from langchain_experimental.text_splitter import SemanticChunker

text = "This is a sample text with multiple sentences."
chunks = [
    {"text": "This is the first part.", "parent_chunk_index": 0},
    {"text": "The second part continues.", "parent_chunk_index": 0},
]
```

## Reference Tables
| Chunking Strategy        | Use Case                          |
|--------------------------|------------------------------------|
| Size-based Splitting     | Content without explicit structure |
| Structure-based Splitting | Documents with clear hierarchy   |

## Key Takeaways
1. Multi-vector indexing improves retrieval accuracy by embedding content from multiple perspectives.
2. Parent-child indexing balances search granularity and contextual relevance through hierarchical chunking.
3. Advanced indexing techniques like semantic chunking enhance retrieval performance but require careful configuration.

## Connects To
- Relates to data ingestion strategies in Chapter 8 on Multimodal RAG.
- Connects with query transformation techniques discussed in Chapter 9 for optimizing user questions.