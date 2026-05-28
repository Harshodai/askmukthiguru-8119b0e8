# Chapter 6: 3 Encoder models in action:

## Core Idea  
Encoder models are fundamental to semantic-based retrieval systems, enabling machines to understand and retrieve information based on meaning rather than just keywords.

## Frameworks Introduced  
- **TF-IDF (Term Frequency-Inverse Document Frequency)**:  
  - When to use: For scoring the importance of terms within documents.  
  - How: Calculates TF-IDF scores by multiplying term frequency in a document with the inverse document frequency across all documents.  

- **Inverted Index**:  
  - When to use: For efficient keyword-based search in large document collections.  
  - How: Maps unique words or tokens to the documents that contain them, enabling quick lookups during retrieval.

## Key Concepts  
- **TF-IDF Score**: A measure of a term's importance within a document and corpus. Higher scores indicate more significant terms for retrieval.  
- **Inverted Index Structure**: A data structure that allows fast retrieval of documents containing specific words by mapping each word to its occurrences.  

## Mental Models  
- Use TF-IDF when you need to score the relevance of terms within a corpus, especially for keyword-based search.  
- Think of an inverted index as a map from words to their locations in the document collection.

## Anti-patterns  
- **Ignoring Context**: Over-relying on keyword matches without considering semantic meaning can lead to irrelevant results.  

## Code Examples  
```python
# Building an Inverted Index

from collections import defaultdict

def build_inverted_index(documents):
    inverted_index = defaultdict(list)
    for doc_id, text in enumerate(documents):
        words = text.split()  # Split into words
        for word in set(words):  # Use set to avoid duplicates
            inverted_index[word].append(doc_id)
    return inverted_index

# Example usage:
documents = [
    "Machine learning approaches leverage neural networks",
    "Classical AI relied on rules and decision trees not neural networks"
]

inverted_index = build_inverted_index(documents)
```

This code demonstrates how to create an inverted index, mapping each unique word to the documents containing it.

## Reference Tables  

| Step | Action                     | Example Code or Explanation               |
|------|----------------------------|------------------------------------------|
| 1    | Tokenize and normalize text   | Split documents into words/tokens         |
| 2    | Calculate TF-IDF scores      | Multiply TF by IDF                       |
| 3    | Build inverted index          | Map words to document IDs                 |

## Key Takeaways  
1. Encoder models are essential for semantic retrieval, enabling machines to understand context beyond keywords.  
2. TF-IDF is a powerful technique for scoring term importance and improving keyword-based search.  
3. Inverted indexes provide an efficient way to map terms to documents for fast retrieval.

## Connects To  
- Relates to NLP pipelines (Chapter 4)  
- Connects to information architecture principles (Chapter 5)