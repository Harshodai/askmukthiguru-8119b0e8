# Chapter 30: Split document into chunks

## Core Idea
This chapter teaches how to improve retrieval systems by transforming documents into question-shaped queries using AI-generated questions from chunked text.

## Frameworks Introduced
- **HyDE**: Transforms the query at search time by generating a hypothetical answer (document-shaped) and using its embedding to search the vector store.
  - When to use: Suitable for stable document collections with high query volumes, as it adds zero latency but requires prep costs.
- **Document Augmentation**: Generates questions from each chunk during preparation and stores them in the vector store.
  - When to use: Appropriate for dynamic document collections or lower traffic where prep cost is manageable.

## Key Concepts
- **Query-shape**: User queries are question-shaped, while stored chunks are declarative.
- **Document-shape**: Declarative chunks require transformation into query-shape via AI generation.
- **Question-generation prompt**: A specific instruction to create query-specific questions from chunk text.
- **Embedding space mismatch**: The gap between query and document shapes affecting retrieval performance.

## Mental Models
- Use HyDE when your system has stable documents and high traffic, as it avoids prep costs with zero latency.
- Use document augmentation for dynamic collections or lower traffic where the upfront cost is justified by reduced query latency.

## Anti-patterns
- Avoid not transforming either queries or documents without addressing the shape mismatch. This can lead to poor retrieval performance due to unaddressed embedding space issues.

## Code Examples
```python
import sentence_transformers as st

# Split text into chunks using a library like sentence-transformers
chunks = st.split_into_chunks(text, chunk_size=512)

# Generate questions from each chunk during preparation
questions = []
for chunk in chunks:
    # Use specific prompts to create query-specific questions
    generated_questions = generate_questions(chunk)
    questions.extend(generated_questions)

# Store questions and their parent chunks in the vector store
question_store = VectorStore()
question_store.add_documents(questions, chunk_indices=[i for i in range(len(chunks))])
```

This code demonstrates splitting text into chunks and generating questions tailored to each chunk.

## Reference Tables

| Framework      | When to Use          | How Implementation Works               |
|----------------|----------------------|----------------------------------------|
| HyDE           | Stable documents, high traffic | Transform user query to document shape at search time using an LLM call. |
| Document Augmentation | Dynamic docs or low traffic | Generate questions from chunks during preparation and store them alongside original content. |

## Key Takeaways
1. Use **document augmentation** for stable collections with high query volumes as it avoids prep costs.
2. Optimize retrieval systems by addressing the shape mismatch between queries and documents.
3. Balance system stability, query volume, and cost when choosing between HyDE and document augmentation.

## Connects To
- Relates to information retrieval techniques like vector search optimization and AI integration in document management systems.