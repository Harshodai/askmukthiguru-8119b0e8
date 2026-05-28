# Chapter 25: Semantic Chunking: Splitting Text

## Core Idea
Semantic chunking replaces fixed-size boundaries with meaning-based splits, using sentence-level embeddings to identify natural topic transitions and create coherent chunks.

## Frameworks Introduced
- **Sentence Embeddings**: Represents each sentence as a vector in an embedding space.
  - When to use: When analyzing text beyond character or word boundaries.
  - How: Convert sentences into vectors using pre-trained models like BERT.

## Key Concepts
- **Sentence Embeddings**: Compact vector representations of entire sentences, capturing their semantic meaning.
- **Distance Thresholds**: A measure of dissimilarity between consecutive sentence embeddings used to identify topic shifts.

## Mental Models
- Use sentence embeddings when analyzing text beyond surface-level structure.
  - Think of chunking as refining content cuts based on semantic flow rather than arbitrary rules.

## Anti-patterns
- **Fixed-size chunks**: Avoid rigid boundaries that ignore meaning shifts, leading to irrelevant mixtures within chunks.
  - Why it fails: Ignores the natural flow and relevance of ideas within text.

## Code Examples
```python
# Calculate sentence embeddings for a chunk of text
import numpy as np
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')
sentences = ["This is a sample sentence.", "Another sentence here."]
embeddings = model.encode(sentences)
print(embeddings)

# Determine distance thresholds using percentile method
distances = [0.1, 0.2, 0.3, 0.4, 0.5]
threshold = np.percentile(distances, 90)
print(threshold)  # Output: 0.48
```

## Reference Tables

| **Method**       | **Threshold Calculation**                                                                 |
|------------------|------------------------------------------------------------------------------------------|
| Percentile       | Threshold at Nth percentile (e.g., 90th percentile)                                   |
| Standard Deviation| Threshold at mean + N standard deviations (N: 1-3)                                    |
| Interquartile Range | Threshold at Q3 + 1.5 * IQR                                                         |

## Key Takeaways
1. Use sentence embeddings to identify natural topic transitions and create coherent chunks.
2. Evaluate distance thresholds using percentile, standard deviation, or interquartile range methods.
3. Avoid fixed-size boundaries; instead, let the text determine its own chunk structure.
4. Balance computational cost by adjusting threshold parameters.

## Connects To
- Relates to vector search from Chapter 1 and chunking limitations in Chapters 4 and 8.