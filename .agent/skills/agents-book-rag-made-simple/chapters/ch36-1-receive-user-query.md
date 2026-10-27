# Chapter 36: 1. Receive user query

## Core Idea
The chapter introduces a hierarchical retrieval system that first searches summaries for relevant sections before retrieving detailed chunks from those sections.

## Frameworks Introduced
- **Hierarchical Retrieval**: Uses metadata linking summaries and chunks to focus retrieval on specific sections.
  - When to use: Large or multi-topic document collections where flat retrieval is too noisy.
  - How: Coarse search with summaries narrows down sections, then fine search retrieves detailed chunks.

## Key Concepts
- **Summary Embeddings**: Cleaner topical representations of sections compared to raw text embeddings.
- **Metadata Linking**: Connects summary page numbers or identifiers to chunk page numbers for semantic alignment.

## Mental Models
- Use metadata linking when dealing with large, multi-topic collections where flat retrieval is too noisy. Think of hierarchical retrieval as a two-step process: first narrow down relevant sections using summaries, then retrieve precise chunks from those sections.

## Anti-patterns
- **Flat Retrieval**: Treats every chunk equally, leading to irrelevant noise in large or diverse document collections. It fails when the collection is too flat or noisy.

## Code Examples
```python
# Example code for metadata linking:
summaries = {
    "section_1": ["page_1", "page_2"],
    "section_2": ["page_3"]
}

chunks = {
    "page_1": "Chunk content from page 1",
    "page_2": "Chunk content from page 2",
    "page_3": "Chunk content from page 3"
}

# Filter chunks based on metadata
relevant_chunks = {k: v for k, v in chunks.items() if k in summaries["section_1"]}
```

- **What it demonstrates**: Metadata linking efficiently narrows down relevant chunks by section identifiers.

## Reference Tables

| Section        | Description                                                                 |
|----------------|-----------------------------------------------------------------------------|
| Coarse Search  | Uses summary embeddings to find matching sections.                           |
| Fine Search    | Filters chunk store based on metadata links, retrieving precise content.     |

## Key Takeaways
1. Use hierarchical retrieval when dealing with large or multi-topic collections.
2. Metadata linking improves accuracy by connecting summaries to their relevant chunks.
3. Summary embeddings provide cleaner topical representations compared to raw text.

## Connects To
- Relates to document indexing strategies and metadata management in information systems.