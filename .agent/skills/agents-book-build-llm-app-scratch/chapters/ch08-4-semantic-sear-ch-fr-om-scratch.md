# Chapter 8: Semantic Search from Scratch

## Core Idea
This chapter teaches how to build a semantic search engine from scratch using text embeddings and distance metrics to enable efficient and accurate information retrieval based on semantic meaning.

## Frameworks Introduced
- **Sentence Transformers**: A library for generating dense vector representations of sentences, particularly useful for sentence-level tasks like semantic search.
  - When to use: For tasks requiring understanding the semantic meaning of entire sentences or documents.
  - How: Load a pre-trained model, encode text into embeddings, and utilize these embeddings for similarity calculations.

## Key Concepts
- **Semantic Search**: A search method that understands the meaning behind queries by using semantic representations of documents.
- **Five Whys Problem-Solving Technique**: A method to dig deeper into why certain features work or don't work in a system.
- **Distance Metrics**: Mathematical tools used to measure similarity between embeddings, such as cosine distance and Euclidean distance.
- **Cross-Encoders**: Architectures that process two input sentences together to calculate their semantic similarity by considering their interaction during encoding.
- **Bi-Encoders**: Architecture combining two encoders to separately encode query and document embeddings before measuring their similarity.

## Mental Models
- Use **Sentence Transformers** when you need to perform semantic search or generate sentence-level embeddings for tasks like document retrieval, summarization, or recommendation systems.

## Anti-patterns
- **Not using embeddings and relying solely on keywords**: This approach misses the semantic context of documents, leading to less accurate search results.

## Code Examples
```python
from sentence_transformers import SentenceTransformer
import torch

# Load a pre-trained model for generating sentence embeddings
model = SentenceTransformer("all-MiniLM-L6-v2")

# Check if CUDA is available and move the model to GPU if possible
if torch.cuda.is_available():
    device = 'cuda'
else:
    device = 'cpu'
model = model.to(device)

# Extract reviews from the dataset
reviews = df_paris['review_text'].tolist()

# Generate embeddings for the reviews with a progress bar
review_embeddings = model.encode(reviews, show_progress_bar=True)

# Print the shape of the resulting embeddings matrix
print(f"Embeddings shape: {review_embeddings.shape}")
```

This code demonstrates how to load sentence embeddings using the `SentenceTransformer` library, check for GPU availability, and generate embeddings for a list of reviews. The resulting embeddings are stored in a matrix that can be used for further analysis.

## Reference Tables

| **Comparison**         | **Cross-Encoders**                                      | **Bi-Encoders**                                         |
|------------------------|----------------------------------------------------------|-----------------------------------------------------------|
| **Architecture**        | Encode both sentences together with [SEP] token           | Separate encoders for query and document embeddings       |
| **Interaction Considered**| Yes, during encoding phase                                   | No, each sentence is encoded independently                |

## Key Takeaways
1. Use text embeddings to represent documents semantically for efficient search.
2. Choose appropriate distance metrics based on the specific requirements of your application.
3. Avoid relying solely on keyword matching; instead, leverage semantic understanding through embeddings.

## Connects To
- Chapter 4: Expedia Hotel Search Engine
- Vector Databases (F AISS)
- Preprocessing and Text Normalization Techniques