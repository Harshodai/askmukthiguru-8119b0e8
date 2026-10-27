# Chapter 11: 1. Receive the generated answer and the source documents

## Core Idea
The chapter introduces a reliable RAG (Retrieval-Augmented Generation) pipeline that incorporates verification steps to enhance accuracy and user trust by filtering noise, checking for hallucinations, and tracing sources.

## Frameworks Introduced
- **Reliable RAG Pipeline**:  
  - When to use: For applications where answer accuracy is critical, such as legal, medical, or financial systems.  
  - How: Adds three verification checkpoints (relevancy grading, hallucination checking, and source highlighting) to a basic RAG pipeline.

## Key Concepts
- **Relevancy Grader**: Filters out irrelevant chunks from the document corpus before they reach the language model.
- **Hallucination Checker**: Verifies that the generated answer is grounded in the provided facts and does not contain fabricated claims.
- **Source Highlighter**: Identifies exact text matches in the source documents to provide users with verifiable sources.

## Mental Models
Use a smaller, faster model for verification tasks (e.g., relevancy grading and hallucination checking) to keep costs manageable while maintaining accuracy. Use a mid-sized model for source highlighting to balance performance and cost.

## Anti-patterns
- **Skipping Verification Steps**: Avoid relying solely on the retrieval and generation steps without verifying the quality of the output, as this can lead to noise or fabricated claims.

## Code Examples
```python
# Example pipeline flow:
1. Receive generated answer and source documents.
2. Send both to a language model for processing.
3. Use a relevancy grader (smaller model) to filter candidate chunks.
4. Apply a hallucination checker (smaller model) to verify groundedness.
5. Implement a source highlighter (mid-sized model) to trace claims back to exact passages.
6. Return verified answer with source attributions.
```

## Reference Tables

| Verification Task                | Model Type         | Description                                                                 |
|----------------------------------|---------------------|-----------------------------------------------------------------------------|
| Relevancy Grading               | Small/Minimal       | Filters out irrelevant chunks before they reach the language model.        |
| Hallucination Checking           | Small/Minimal       | Verifies that generated answers are grounded in provided facts.          |
| Source Highlighting             | Mid-Sized           | Identifies exact text matches in source documents for user verification.  |

## Key Takeaways
1. Enhancing RAG with verification steps improves accuracy and builds user trust.
2. Verification tasks (relevancy grading, hallucination checking, source highlighting) should be implemented to filter noise and catch fabricated claims.
3. Smaller models are sufficient for verification tasks, keeping costs low while maintaining performance.

## Connects To
- Relates to the concept of "Verification Steps" in Chapter 10 on improving RAG systems through quality control measures.