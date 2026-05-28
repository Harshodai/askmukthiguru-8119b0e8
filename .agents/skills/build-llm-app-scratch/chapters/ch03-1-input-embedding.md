# Chapter 3: 1. Input Embedding:

## Core Idea  
Input embedding transforms raw text into dense numerical vectors that capture semantic meaning, enabling machines to understand language through vector representations.

## Frameworks Introduced  
- **Sparse Vectors**: Uses one-hot encoding with high-dimensional sparse arrays (e.g., [1,0,0] for "apple").  
  - When to use: When dealing with categorical data where individual word identities are key.  
  - How: Assign a unique index to each word and create a vector with all zeros except for the corresponding position.  

- **Dense Vectors**: Utilizes lower-dimensional arrays with nuanced numerical values (e.g., [0.9, 0.3, 0.2] for "apple").  
  - When to use: When capturing semantic relationships between words is crucial.  
  - How: Represents each word as a continuous vector where similar words are closer together in space.

## Key Concepts  
- **Input Embedding**: The process of converting raw text into dense numerical vectors.  
- **One-Hot Encoding**: A method for sparse vectors where each word is represented by a unique index in a high-dimensional space.  
- **Word Embeddings**: Numerical representations of words that capture semantic and syntactic information.  
- **Numerical Representation**: The conversion of linguistic data into numerical arrays for computational processing.

## Mental Models  
Use one-hot encoding when you need to represent individual word identities without capturing their nuanced meanings. Think of sparse vectors as isolating words in a vast, mostly empty space. Use dense vectors when you want to model the relationships and context between words, placing similar words close together in this numerical space.

## Anti-patterns  
- **Sparse Vectors**: Avoid using one-hot encoding when you need to capture semantic relationships between words, as it may lead to a loss of contextual information.

## Code Examples  
```python
# Example of One-Hot Encoding
vocabulary = ["apple", "banana", "orange"]
word_to_index = {"apple": 0, "banana": 1, "orange": 2}
sparse_embedding = {word: [1 if i == word_to_index[word] else 0 for i in range(len(vocabulary))] 
                    for word in vocabulary}

# Example of Dense Embedding
dense_embedding = {
    "apple": [0.9, 0.3, 0.2],
    "banana": [0.8, 0.7, 0.1],
    "orange": [0.7, 0.5, 0.9]
}
```

This demonstrates how sparse vectors use binary values to represent word identities and dense vectors use continuous numerical values to capture semantic relationships.

## Reference Tables  

| **Vector Type** | **Characteristics** | **Use Case** |
|------------------|--------------------|--------------|
| Sparse Vectors   | High-dimensional, mostly zeros | Individual word identity representation |
| Dense Vectors    | Lower-dimensional, nuanced values | Capturing semantic and contextual relationships |

## Key Takeaways  
1. Input embedding is essential for transforming text into a form machines can understand.  
2. Choose between sparse or dense vectors based on whether you prioritize word identity (sparse) or semantic context (dense).  
3. Avoid sparse vectors when modeling word relationships, as they may lead to information loss.

## Connects To  
- Relates to search engine applications in Chapter 3, where dense embeddings improve retrieval systems by capturing contextual meaning.