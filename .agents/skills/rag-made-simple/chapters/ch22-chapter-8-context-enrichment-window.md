# Chapter 23: Context Enrichment Window

## Core Idea
The context enrichment window enhances retrieval accuracy by expanding retrieved chunks with surrounding text, preventing information loss at chunk boundaries.

## Frameworks Introduced
- **Context Enrichment Window**:  
  - When to use: After retrieving a chunk using similarity search.  
  - How: Expand the retrieved chunk by including adjacent chunks from the original document.

## Key Concepts
- **Chunking**: The process of splitting documents into fixed-size pieces for embedding and retrieval.
- **Overlap**: A technique to preserve information at chunk boundaries, though it is not sufficient on its own.
- **Context Enrichment Window**: A method to expand retrieved chunks by including surrounding text from the original document.

## Mental Models
- Use context enrichment window when you want to ensure that AI responses are complete and accurate.  
  Think of context enrichment window as a spotlight that widens to show more of the scene, allowing readers to follow the conversation fully.

## Anti-patterns
- **Chunking-only approach**: This fails because it cuts off important context before and after the retrieved fragment, leading to incomplete or misleading information.

## Code Examples
```
# Example Pseudocode for Context Enrichment Window

def expand_context(chunk, document, num_before=1, num_after=1):
    """
    Expands a chunk by including surrounding chunks from the original document.
    
    Args:
        chunk (str): The retrieved chunk of text.
        document (str): The full text of the document.
        num_before (int): Number of preceding chunks to include.
        num_after (int): Number of following chunks to include.
        
    Returns:
        str: Expanded context passage containing the original chunk and surrounding text.
    """
    # Split the document into chunks
    all_chunks = split_into_chunks(document)
    
    # Find the index of the retrieved chunk
    chunk_index = find_chunk_index(all_chunks, chunk)
    
    # Collect the expanded context by including surrounding chunks
    expanded_context = []
    for i in range(max(0, chunk_index - num_before), min(len(all_chunks), chunk_index + num_after)):
        expanded_context.append(all_chunks[i])
        
    return " ".join(expanded_context)
```

# Reference Tables

| Parameter | Description |
| --- | --- |
| `num_before` | Number of preceding chunks to include in the context enrichment window. |
| `num_after` | Number of following chunks to include in the context enrichment window. |

## Key Takeaways
1. Use context enrichment window when you want to ensure that AI responses are complete and accurate.
2. Expand retrieved chunks by including surrounding text from the original document.
3. Avoid chunking-only approaches that cut off important context.

## Connects To
- Relates to chunking, overlap, vector search, and contextual chunk headers in Chapter 1 and Chapter 7.