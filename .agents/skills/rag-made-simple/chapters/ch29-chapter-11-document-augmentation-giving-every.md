# Chapter 29: Chapter 11: Document Augmentation: Giving Every

## Core Idea
Document augmentation enhances retrieval by pre-generating questions for each chunk of text, ensuring user queries align with stored information in a question format.

## Frameworks Introduced
- **Document Augmentation**: A method to improve RAG systems by adding generated questions alongside chunks during preparation.
  - When to use: When dealing with mismatched query and document formats (questions vs. declarative text).
  - How: Pre-generate questions for each chunk, store them in the vector store.

## Key Concepts
- **Generated Questions**: Questions precomputed for each chunk to match potential user inquiries.
- **Embedding Space Alignment**: Both questions and chunks exist in the same space, facilitating direct matches.
- **Metadata Linking**: Each question points back to its parent chunk for context retrieval.

## Mental Models
Use document augmentation when you need to align user queries with content presentation. The key is pre-generating questions during preparation to avoid query reshaping issues.

## Anti-patterns
- Avoid traditional RAG without augmenting for questions, as it leads to mismatched retrieval gaps.

## Code Examples
```python
def generate_questions(chunk: str) -> List[str]:
    """Generate multiple questions that could be answered by the chunk."""
    return [
        "What does this explain?",
        "Can you summarize the key points?",
        "How does this relate to other topics?"
    ]
```
- **What it demonstrates**: Shows how to create a function that generates questions for each chunk, enhancing query matching.

## Reference Tables
| Parameter | Decision Table |
|-----------|----------------|
| Chunk Size | Fixed or semantic-based |
| Question Granularity | Fragment-level (precise) or document-level (broad) |

## Key Takeaways
1. Pre-generate questions for each chunk to align user queries with content.
2. Store these questions alongside chunks in the vector store for direct query matching.
3. Metadata links ensure retrieved context remains relevant.

This chapter connects to earlier discussions on RAG pipelines and information retrieval techniques, offering a proactive solution to query-document mismatch issues.