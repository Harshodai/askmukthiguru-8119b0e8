# Chapter 24: Contextual Chunk Headers and Enrichment Windows

## Core Idea
This chapter introduces two techniques—contextual chunk headers and context enrichment windows—that enhance document chunking by adding vertical (document-level) and horizontal (local) context, respectively. These complementary approaches improve the completeness of answers while maintaining retrieval efficiency.

## Frameworks Introduced
- **Contextual Chunk Headers**: Adds document-level information to each chunk.
  - When to use: For long documents where ideas span multiple paragraphs.
  - How: Prepend document-level metadata (title, summary, section path) to each chunk.
  
- **Context Enrichment Window**: Expands chunks with surrounding text for completeness.
  - When to use: For systems requiring precise answers and accuracy.
  - How: Expand retrieved chunks by including neighboring chunks during retrieval.

## Key Concepts
- **Vertical Context (Chunk Headers)**: Provides document-level information, answering "which document is this from and what section?" 
- **Horizontal Context (Enrichment Window)**: Adds surrounding text context, answering "what was the full thought being expressed here?"

## Mental Models
- Use contextual chunk headers when dealing with long documents where ideas span multiple paragraphs.
  - Think of chunk headers as metadata that enrich each chunk with document-level context.

- Use context enrichment windows when precision and completeness are critical during retrieval.
  - Think of context windows as expanding retrieved chunks by including related neighboring chunks.

## Anti-Patterns
- **Avoid self-contained chunks (Proposition Chunking)**: This approach creates self-contained units but requires an LLM for expansion, making it less efficient for systems where preparation costs are high.

## Code Examples
```python
# Example code to prepend chunk headers and expand with context windows

def add_headers_and_window(chunk):
    # Prepend document-level metadata (e.g., title, summary)
    header = f"**Context Header:** {chunk['title']} - {chunk['summary']}\n\n"
    enriched_chunk = header + chunk['text']
    
    # Expand retrieval with context window
    left_context = retrieve_previous_chunks(1) if len(retrieve_previous_chunks(1)) > 0 else ""
    right_context = retrieve_next_chunks(1) if len(retrieve_next_chunks(1)) > 0 else ""
    final_chunk = f"**Context Window Enrichment:** {left_context}{enriched_chunk}{right_context}"
    
    return final_chunk
```

## Reference Tables

| Parameter          | Value/Decision |
|--------------------|----------------|
| When to use headers | Long documents with multiple paragraphs. |
| Chunk size for headers | Under 500 characters for precise matching. |
| Window size        | Configurable, typically 1-2 neighbors per side. |

## Key Takeaways
1. Use contextual chunk headers to add document-level context when dealing with long, multi-paragraph documents.
2. Enrich retrieved chunks with context windows to expand partial answers into complete ones during retrieval.
3. Combine both techniques for optimal results in knowledge bases requiring both vertical and horizontal context.

## Connects To
- Relates to knowledge base organization (Chapter 7) and chunking techniques (Chapter 4).