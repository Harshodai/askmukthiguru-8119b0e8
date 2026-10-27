# Chapter 23: 169 Summary

## Core Idea  
This chapter delves into advanced Retrieval-Augmented Generation (RAG) techniques to build robust, reliable, and scalable AI systems capable of handling complex queries.

## Frameworks Introduced  
- **Multi-vector Retrieval**: Expands beyond single vector retrieval by considering multiple vectors for context-aware search.  
  - When to use: When data is structured or hierarchical in nature.  
  - How: Leverages multiple embedding layers to enhance retrieval accuracy.  

- **Context Expansion**: Enhances retrieval by expanding the context window, ensuring coherence across retrieved documents.  
  - When to use: When maintaining document coherence is critical.  
  - How: Uses sliding windows or summarization techniques to expand context.  

- **HyDE (Hypothetical Document Embeddings)**: Rewrites queries to generate hypothetical documents for better retrieval.  
  - When to use: When query specificity is an issue.  
  - How: Creates embeddings for rewritten queries to improve retrieval accuracy.  

- **Reciprocal Rank Fusion (RRF)**: Combines outputs from multiple data sources to refine final answers.  
  - When to use: When integrating results from different data stores.  
  - How: Averages or fuses scores from vector databases, SQL systems, etc., for improved reliability.  

## Key Concepts  
- **Chunking**: Breaking documents into manageable fragments for efficient retrieval and processing.  
- **Metadata Filtering**: Improves retrieval by filtering based on document attributes like date, author, or category.  
- **Sliding Window Context Compression**: Maintains conversation context by keeping only the last N turns.  
- **Summarization**: Condenses historical data to stay within token limits while retaining essential information.  

## Mental Models  
Use multi-vector retrieval when your data is structured or hierarchical in nature. Think of reranking as a way to refine results for better relevance and coherence. Avoid keyword-only queries by rewriting them with more context, such as using HyDE.

## Anti-patterns  
- **Ignoring Context During Reranking**: This can lead to irrelevant results if not properly considered.  

## Code Examples  
```python
from langchain.schema import HumanMessage, AIMessage

# Example of appending messages to maintain conversation context
def chat_prompt_template.from_messages(messages):
    return f"Respond based on this conversation:\n{messages}"
```

This demonstrates how a custom prompt template can structure conversations using predefined message objects.

## Reference Tables  

| Data Structure | Technique Suggested | Rationale |
|----------------|--------------------|----------|
| Text           | Chunking           | Improves retrieval efficiency. |
| HTML          | Context Expansion  | Maintains semantic coherence. |
| Markdown       | Multi-vector Retrieval | Handles structured data effectively. |

## Key Takeaways  
1. Use multi-vector retrieval for structured or hierarchical data to enhance retrieval accuracy.  
2. Rewrite queries using HyDE to improve specificity and relevance.  
3. Implement context compression techniques like sliding windows or summarization to manage conversation length.  

## Connects To  
- Relates to previous discussions on RAG basics (Chapter 169).  
- Prepares for advanced evaluation and deployment strategies in future chapters.