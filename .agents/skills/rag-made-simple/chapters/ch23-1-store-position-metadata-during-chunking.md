# Chapter 23: 1. Store Position Metadata During Chunking  

## Core Idea  
Chunk documents into small pieces while storing their sequential indices for precise retrieval and context expansion.  

## Frameworks Introduced  
- **Context Window Expansion**:  
  - When to use: After retrieving chunks via similarity search, expand the result with neighboring chunks to enhance context.  
  - How: Fetch a window of chunks around the retrieved chunk, sort them by index, and concatenate them while trimming overlaps.  

## Key Concepts  
- **Chunk Metadata**: Stores the original document's position for efficient lookup during retrieval.  
- **Similarity Search**: Retrieves top-K most related chunks based on embeddings.  
- **Window Size**: Determines how many neighboring chunks are included in the expanded passage (e.g., 3 or 5 chunks).  
- **Overlap Trimming**: Removes duplicated text at chunk boundaries to create seamless concatenation.  

## Mental Models  
Use chunking with metadata when you need precise retrieval, and expand windows for context. Think of Context Window Expansion as a method to merge retrieved chunks into a coherent passage while avoiding duplication.  

## Anti-patterns  
- **Naive Chunk Concatenation**: Avoid simply joining chunks without trimming overlaps, as it leads to duplicated text in the middle.  

## Code Examples  
```python
def expand_retrieved_chunk(query_index, window_size=3):
    start = query_index - window_size // 2
    end = query_index + window_size // 2
    fetched_chunks = fetch_chunks(start, end)
    fetched_chunks.sort(key=lambda x: x['index'])
    
    passage = fetched_chunks[0]['text']
    for chunk in fetched_chunks[1:]:
        # Trim overlap and append
        passage = trim_overlap(passage, chunk['text'])
        passage = passage[len(overlap):]
    return passage
```

- **What it demonstrates**: Expands a retrieved chunk's context by including neighboring chunks and trimming overlaps to create a clean, continuous text.  

## Reference Tables  
| Parameter      | Description                     | Impact on Context and Noise |
|----------------|----------------------------------|------------------------------|
| Window Size    | Number of neighbors (e.g., 3 or 5) | Larger windows increase context but may include more noise. |

## Key Takeaways  
1. Use chunking with metadata for precise retrieval of small, focused chunks.  
2. Expand retrieved chunks by including neighboring chunks within a window size to enhance context.  
3. Trim overlaps during concatenation to avoid duplicated text in the middle.  
4. Choose an appropriate window size based on document structure (longer windows for flowing texts, smaller for short sections).  
5. Integrate chunk metadata and context expansion into your document processing pipeline for better search and comprehension.  

## Connects To  
- Metadata Management: Ensures chunks are tagged with their original positions.  
- Vector Stores: Stores chunk embeddings alongside their metadata for efficient similarity search.