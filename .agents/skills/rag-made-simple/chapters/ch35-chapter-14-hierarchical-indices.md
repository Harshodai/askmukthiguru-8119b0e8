# Chapter 35: Hierarchical Indices

## Core Idea
Hierarchical indexing organizes retrieval into two levels: summaries for coarse search and detailed chunks for fine-grained results, improving efficiency in large knowledge bases.

## Frameworks Introduced
- **Hierarchical Indexing with Summaries and Detailed Chunks**  
  - When to use: Large-scale knowledge bases requiring efficient retrieval.  
  - How: Use summaries for initial coarse search and detailed chunks for precise results.

## Key Concepts
- **Summary**: A high-level signpost summarizing a document section's main topic.
- **Chunk**: A detailed piece of information within a section, tagged with metadata for context.
- **Metadata**: Links between summaries and chunks, indicating the source section.

## Mental Models
- Use summaries first when dealing with large knowledge bases to narrow down relevant sections.  
  Think of hierarchical indexing as navigating a department store: use a directory (summaries) to find aisles (chunks).

## Anti-patterns
- **Flat Indexing**: Fails to structure search, leading to scattered and irrelevant results.

## Code Examples
```python
# Example metadata linking in practice:
metadata = {
    "summary_id_1": ["chunk_id_1", "chunk_id_2"],
    "summary_id_2": ["chunk_id_3", "chunk_id_4"]
}
```

## Reference Tables

| Component        | Function                                      |
|------------------|------------------------------------------------|
| **Summary Index** | Coarse search for relevant sections            |
| **Chunk Index**  | Fine-grained search within selected sections   |

## Key Takeaways
1. Use hierarchical indexing to improve retrieval efficiency in large knowledge bases.
2. Metadata links are crucial for connecting summaries and chunks.
3. Avoid flat indexing; prioritize structured two-level search.

## Connects To
- Relates to information architecture and efficient search strategies in technical documentation.