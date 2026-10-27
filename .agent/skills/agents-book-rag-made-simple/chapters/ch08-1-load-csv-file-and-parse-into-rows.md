# Chapter 8: 1. Load CSV file and parse into rows

## Core Idea  
This chapter demonstrates how to apply RAG (Retrieval-Augmented Generation) to structured data like CSV files by serializing rows into text for semantic search, enabling natural language queries that retrieve relevant records based on meaning rather than exact matches.

## Frameworks Introduced  
- **CSV Query Processing Algorithm Sketch**:  
  - When to use: For processing and answering questions over structured CSV data.  
  - How: 1. Embed the question into a vector; 2. Search for nearest record vectors; 3. Retrieve corresponding text representations; 4. Pass question + retrieved records to LLM for an answer.

## Key Concepts  
- **Field Serialization**: Converting rows into readable text with field names (e.g., "First Name: Sheryl. Company: Rasmussen Group") to improve embedding quality and semantic understanding.  

## Mental Models  
- Use CSV serialization when you need to handle structured data with meaningful field relationships. Think of it as transforming tabular data into natural language sentences for better semantic search.

## Anti-patterns  
- **Avoid exact-match queries**: When a traditional database query is sufficient, RAG introduces unnecessary complexity and cost without providing additional value.

## Code Examples  
```python
import pandas as pd
from sklearn.preprocessing import LabelEncoder

# Load CSV file
df = pd.read_csv('customer_data.csv')

# Serialize rows into labeled text
def serialize_row(row):
    return f"Name: {row['First Name']}. Company: {row['Company']}"

serialized_rows = df.apply(serialize_row, axis=1).tolist()
```

- **What it demonstrates**: Converts structured data into a format suitable for embedding and semantic search.

## Reference Tables  

| Parameter | Decision |
|---|---|
| Dataset Size | Use vector store for efficient retrieval (e.g., FAISS) |
| Embedding Cost | One embedding per row; scale with large datasets |

## Key Takeaways  
1. **Field serialization** improves retrieval quality by preserving field relationships and semantic meaning in structured data.
2. **RAG scales well** for large tables but requires careful consideration of embedding costs for very high volumes of data.
3. **Use RAG when queries are fuzzy or require semantic understanding**, especially for customer, product, or employee databases.

## Connects To  
- Relates to document RAG and vector store considerations in structured data processing.