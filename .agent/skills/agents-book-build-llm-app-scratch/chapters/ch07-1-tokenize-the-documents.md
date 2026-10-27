# Chapter 7: Semantic Search and TF-IDF

## Core Idea
This chapter introduces semantic search as an advanced method to enhance keyword search by understanding the context and meaning of queries, using techniques like TF-IDF for scoring relevance.

## Frameworks Introduced
- **TF-IDF (Term Frequency-Inverse Document Frequency)**:
  - When to use: For ranking documents based on keyword relevance.
  - How: Calculates term frequency (TF) and inverse document frequency (IDF) scores to determine relevance.
  
- **Inverted Index**:
  - When to use: For efficient keyword-based searches by mapping terms to documents they appear in.

## Key Concepts
- **TF-IDF**: A scoring mechanism that reflects how important a word is to a document in a collection of documents.
- **Inverted Index**: A data structure that maps each unique term to the documents containing it, enabling fast lookups.

## Mental Models
Use TF-IDF when you need to rank documents based on keyword relevance. Avoid exact keyword matching without semantic understanding.

## Anti-patterns
**Relying solely on exact keywords**: Can miss relevant content that doesn't match exactly but is semantically related.

## Code Examples
```python
# Create inverted index:
from nltk import word_tokenize
import math

def create_inverted_index(sentences):
    inverted_index = {}
    for idx, doc in enumerate(sentence_tokens):
        for word in doc:
            if word not in inverted_index:
                inverted_index[word] = []
            inverted_index[word].append(idx)
    return inverted_index

# TF-IDF function:
def tfidf(word, document, indexed_docs):
    tf = document.count(word) / len(document)
    df = len(indexed_docs.get(word, [])) if word in indexed_docs else 0
    idf = math.log(len(indexed_docs), df + 1) if df > 0 else 0
    return tf * idf

# Example usage:
sentences = ["The cat is playing in the garden", 
             "A dog and a cat are good pets",
             "Cats love to chase mice"]
tokenized_docs = [word_tokenize(d) for d in sentences]
inverted_index = create_inverted_index(tokenized_docs)
scores = {i: 0 for i, _ in enumerate(tokenized_docs)}
for q_word in ["machine learning"]:
    if q_word in inverted_index:
        for idx in indexed_docs[q_word]:
            scores[idx] += tfidf(q_word, tokenized_docs[idx], inverted_index)
```

## Reference Tables
| Term       | Definition                                                                 |
|------------|-----------------------------------------------------------------------------|
| TF-IDF     | A scoring method combining term frequency and inverse document frequency.    |
| Inverted Index | Maps each unique term to the documents containing it.                     |

## Key Takeaways
1. Use TF-IDF for efficient keyword-based searches by calculating relevance scores.
2. Understand the components of TF-IDF: Term Frequency (TF) and Inverse Document Frequency (IDF).
3. Apply inverted indexes for quick document lookups during searches.

## Connects To
- Information Retrieval Basics
- BM 25 Algorithm