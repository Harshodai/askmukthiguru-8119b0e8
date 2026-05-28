```markdown
# Chapter 28: Contextual Compression in Search Systems

## Core Idea
The chapter introduces contextual compression as a method to enhance relevance by extracting only the pertinent sentences from retrieved chunks, combining it with relevancy grading for improved efficiency and precision.

## Frameworks Introduced
- **Contextual Compression**: This technique involves using an LLM to extract relevant sentences from each chunk based on the query. It operates at the sentence level within each chunk.
  - When to use: Suitable for scenarios where retrieved chunks are broad or noisy, containing tangential information.
  - How: The process includes grading and compressing steps to refine relevance.

## Key Concepts
- **Retrieved Chunks**: These are topically relevant but often contain extraneous sentences. They need to be processed to extract only the useful parts.
- **Relevancy Grading**: A binary filter that keeps or discards entire chunks based on relevance, used before compression for efficiency.
- **Contextual Compression**: Enhances precision by extracting only the necessary sentences from each chunk after grading.

## Mental Models
- Use LLMs for both grading and compressing to balance efficiency and precision. Understand that context is crucial in determining relevance.

## Anti-patterns
- Avoid using only one method (grading or compression) without combining them, as this may lead to inefficiency or loss of useful information.

## Code Examples
```python
# Pseudocode for Contextual Compression Process
def process_query(query):
    # Step 1: Retrieve top-K chunks from vector store
    retrieved_chunks = retrieve_top_k(query)
    
    # Step 2: Grade each chunk to remove irrelevant ones
    graded_chunks = []
    for chunk in retrieved_chunks:
        if is_relevant(chunk, query):
            graded_chunks.append(chunk)
    
    # Step 3: Compress each chunk to extract relevant sentences
    compressed_excerpts = []
    for chunk in graded_chunks:
        excerpt = contextual_compress(chunk, query)
        if excerpt:
            compressed_excerpts.append(excerpt)
    
    # Step 4: Pass compressed excerpts through generation LLM
    answer = generate回答(compressed_excerpts + [query])
    
    return answer
```

## Reference Tables

| **Framework** | **Formulation** | **When to Use** | **How** |
|---------------|------------------|-----------------|----------|
| Contextual Compression | Extracts relevant sentences from each chunk based on query. | Broad or noisy chunks, specific queries. | LLM used at query time for sentence extraction. |
| Relevancy Grading | Keeps or discards entire chunks based on relevance. | Noisy chunks with well-focused content. | Binary filter applied during retrieval phase. |

## Key Takeaways
1. Contextual compression enhances relevance by extracting pertinent sentences from retrieved chunks, combining it with relevancy grading for efficiency.
2. Use LLMs for both grading and compressing to balance precision and cost.
3. Understand the context in which chunks are retrieved to improve query relevance.

## Connects To
- Relates to search systems and information retrieval techniques discussed earlier.
```