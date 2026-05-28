# Chapter 7: RAG for Structured Data: When Spreadsheets Meet Semantic Search

## Core Idea
The chapter introduces adapting the RAG (Retrieval-Augmented Generation) pipeline for structured data like CSV files, treating each row as a self-contained document to avoid splitting records and mixing fields.

## Frameworks Introduced
- **Structured Data RAG**: 
  - When to use: For tabular datasets where rows represent complete records.
  - How: Convert each row into a readable text description before embedding and storing in a vector database.

## Key Concepts
- **Field Serialization**: Converting a row of structured data into a human-readable text string that preserves all information.
- **Vector Store for Records**: Storing each record as a vector to enable semantic similarity search without chunking.

## Mental Models
- Use field serialization when working with tabular datasets to preserve record boundaries and improve retrieval accuracy.
- Think of structured data as inherently organized, eliminating the need for character-based chunking.

## Anti-patterns
- **Avoid mixing fields**: Do not split rows into chunks that mix records from different entries; each row should be treated as a complete unit.

## Code Examples
```python
# Example of field serialization in pseudocode
def serialize_row(row):
    return f"{row['first_name']}: {row['last_name']}. Company: {row['company']}. City: {row['city']}. Country: {row['country']}. Email: {row['email']}."

# Example vector store setup
vector_store = VectorStore()
for row in csv_rows:
    text = serialize_row(row)
    vector = model.encode(text)
    vector_store.add(text, vector)
```

## Reference Tables

| **Term**         | **Definition/Action**                                                                 |
|-------------------|---------------------------------------------------------------------------------------|
| Field Serialization | Converting a structured data row into a readable text string preserving all information. |
| Vector Store     | A database storing vectors for each record to enable semantic similarity search. |

## Key Takeaways
1. Treat each row in a CSV as a self-contained document to avoid mixing fields and improve retrieval accuracy.
2. Serialize rows into readable text before embedding them into a vector store.
3. Use structured data RAG when working with tabular datasets to leverage semantic search capabilities.

## Connects To
- Relates to chapter 1 on Simple RAG, extending its principles to structured data.
- Connects to vector stores and semantic search concepts discussed in previous chapters.