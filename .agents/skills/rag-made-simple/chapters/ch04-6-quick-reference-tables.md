# Chapter 4: Smarter Chunking

## Core Idea  
The chapter introduces smarter chunking techniques that improve retrieval accuracy by decomposing documents into atomic facts with context.

## Frameworks Introduced  
- **Proposition Chunking**: Decomposes text into chunks containing atomic facts, each with a subject-predicate-object structure.  
  - When to use: When dealing with structured or semantic data.  
  - How: Split text based on predicate boundaries and assign metadata like entity types and source context.

## Key Concepts  
- **Contextual Headers**: Metadata added to chunk headers that describe the chunk's content, such as entity type or source location.  
- **Context Enrichment Windows**: Expanded retrieved passages that include surrounding context to improve relevance and accuracy.  
- **Semantic Chunking**: Splits text into chunks based on changes in meaning rather than fixed length or boundaries.

## Mental Models  
- Use proposition chunking when you need atomic facts with metadata for precise retrieval.  
- Add contextual headers to chunks to capture their source and domain-specific information.  
- Enrich retrieved data with surrounding context to enhance relevance.

## Anti-patterns  
- **Arbitrary Document Splitting**: Avoid splitting documents into arbitrary chunks without considering meaning or context, as it can reduce retrieval quality.

## Code Examples  
```python
from sentence_transformers import SentenceTransformer

def proposition_chunking(text: str) -> List[Dict]:
    """Splits text into atomic facts with metadata."""
    model = SentenceTransformer('all-MiniLM-L6-v2')
    embeddings = model.encode(text.split())
    
    chunks = []
    for i, (emb, token) in enumerate(zip(embeddings, text.split())):
        # Add entity type and source context as metadata
        chunk = {
            'text': token,
            'metadata': {
                'entity_type': get_entity_type(token),
                'source_context': f"Token {i} in document"
            }
        }
        chunks.append(chunk)
        
    return chunks
```

This demonstrates how to split text into proposition chunks with metadata for improved retrieval.

## Reference Tables  
| Chunking Method          | Features                                      | When to Use                     |
|--------------------------|-------------------------------------------------|----------------------------------|
| Basic Splitting         | Splits documents into fixed-length chunks       | Simple, fast document preparation |
| Proposition Chunking    | Includes atomic facts with entity metadata     | Needs precise retrieval accuracy  |
| Contextual Headers       | Adds metadata about chunk context              | Requires domain-specific knowledge |
| Semantic Enrichment      | Expands retrieved passages with surrounding text| Enhances relevance in ambiguous queries |

## Key Takeaways  
1. Use proposition chunking to split documents into atomic facts for precise retrieval.  
2. Add contextual headers to chunks to capture their source and domain information.  
3. Enrich retrieved data with surrounding context to improve relevance.  
4. Avoid arbitrary document splitting as it can reduce retrieval quality.  

## Connects To  
- Relates to foundational chunking techniques in Chapter 1.  
- Builds upon advanced retrieval strategies in later chapters.