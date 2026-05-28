# Chapter 20: Contextual Chunk Headers: Giving Every Chunk Its Origin Story

## Core Idea
Contextual chunk headers preserve document-level context for each chunk, ensuring retrieval systems understand where text originates.

## Frameworks Introduced
- **Running Header**: Anchors chunks to their source by prepending a small piece of context (e.g., document title).  
  - When to use: Any scenario involving chunked documents.  
  - How: Prepend headers like "Document Title: <chunk>" before embedding.

## Key Concepts
- **Contextual Chunk Header**: A header added to each chunk that includes minimal context, such as a document title.
- **Header Richness**: Varies from simple titles to full section paths or summaries for varying needs.

## Mental Models
- Use a running header when chunking documents.  
  - Think of it as adding page headers in a printed book; they keep chunks anchored even when torn out.

## Anti-patterns
- **Chunks losing context**: When chunks rely solely on pronouns without surrounding context, reducing their meaning.

## Code Examples
```python
def add_context_header(header: str, chunk: str) -> str:
    """
    Prepend a contextual header to a chunk for enhanced retrieval.
    
    Args:
        header (str): The header text, e.g., "Document Title."
        chunk (str): The raw chunk content.
        
    Returns:
        str: The chunk with the header added at the beginning.
    """
    return f"{header}: {chunk}"
```

## Reference Tables

| **Parameter**       | **Description**                                                                 |
|---------------------|---------------------------------------------------------------------------------|
| **Header Type**     | Minimal (e.g., document title) vs. richer context (e.g., summary or section path). |
| **Use Case**        | Quick solutions for minimal context preservation or detailed analysis with full context. |

## Key Takeaways
1. Add contextual headers to chunks to preserve their identity during retrieval.
2. Use minimal headers like document titles for quick solutions.
3. Consider richer headers for more detailed information needs.

## Connects To
- Relates to chapter 1 on chunking, embeddings, and vector search techniques in the knowledge graph setup.