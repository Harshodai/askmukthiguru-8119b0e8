# Chapter 14: Using BERTopic for Text Clustering and Topic Modeling

## Core Idea
This chapter demonstrates how to use BERTopic, a modular framework combining embeddings, dimensionality reduction, clustering, and topic modeling, to analyze and cluster large collections of textual documents. It emphasizes the importance of fine-tuning topic representations using techniques like reranking with TF-IDF, KeyBERTInformed reranking, and Maximal Marginal Relevance (MMR). Additionally, it showcases how generative models can enhance topic interpretability by creating human-readable labels.

## Frameworks Introduced
- **BERTopic**: A modular framework combining embeddings, dimensionality reduction, clustering, and topic modeling.
  - When to use: For analyzing and clustering large collections of textual documents while preserving semantic meaning.
  - How: 
    1. Convert text into dense vector representations using BERT models (e.g., sentence-transformers/all-mpnet-base-v2).
    2. Apply dimensionality reduction techniques like UMAP to simplify high-dimensional data.
    3. Use clustering algorithms like HDBSCAN for grouping similar documents.
    4. Enhance topic representations with reranking techniques and generative models.

## Key Concepts
- **Embeddings**: Numerical representations of text that capture semantic meaning, created using BERT models.
- **Dimensionality Reduction**: Techniques like UMAP to reduce high-dimensional data into a lower-dimensional space for clustering.
- **Clustering Algorithms**: Such as HDBSCAN, which groups documents based on their similarity in the reduced embedding space.
- **Topic Modeling**: The process of identifying latent themes or topics within a collection of documents using techniques like reranking and generative models.

## Mental Models
- Use BERTopic when you need to analyze and cluster large collections of textual documents while preserving semantic meaning. It helps identify latent themes and provides human-readable topic labels by combining embeddings, dimensionality reduction, clustering, and generative models.
- Think of BERTopic as a comprehensive tool that integrates multiple steps from text preprocessing to final topic interpretation.

## Anti-patterns
- Avoid using traditional supervised learning methods for topic modeling when unsupervised approaches like BERTopic can provide more interpretable results by leveraging semantic relationships in the data.

## Code Examples
```python
# Example code snippet demonstrating the use of BERTopic
from bertopic import BERTopic
import sentence-transformers

# Load documents and convert to embeddings using a BERT model
embeddings = sentence-transformers(all-mpnet-base-v2).encode(documents)

# Apply dimensionality reduction
reduced_embeddings = UMAP(n_components=2, random_state=42).fit_transform(embeddings)

# Create topic clusters
topic_model = BERTopic(
    embedding_model=sentence-transformers.all-mpnet-base-v2,
    umap_model=UMAP(n_components=2, random_state=42),
    hdbscan_model=HDBSCAN(min_samples=50, metric="cosine", cluster_selection="eom")
)
topic_model.fit(reduced_embeddings)

# Get topic assignments
labels = topic_model.labels_

# Visualize topics and documents
topic_model.visualize_documents(
    titles,
    topics=range(topic_model.get_num_topics()),
    reduced_embeddings=reduced_embeddings,
    width=1200
)
```

## Reference Tables
| Parameter        | Value/Setting                          |
|------------------|-----------------------------------------|
| BERT Model       | sentence-transformers/all-mpnet-base-v2 |
| Dimensionality Reduction | UMAP(n_components=2, random_state=42) |
| Clustering Algorithm | HDBSCAN(min_samples=50, metric="cosine", cluster_selection="eom") |

## Key Takeaways
1. Use BERT models to create dense vector representations of text.
2. Apply dimensionality reduction techniques like UMAP to simplify high-dimensional data for clustering.
3. Utilize clustering algorithms like HDBSCAN to group documents based on their semantic similarity.
4. Enhance topic interpretability by reranking topics with TF-IDF, KeyBERTInformed reranking, and Maximal Marginal Relevance (MMR).
5. Leverage generative models like Flan-T5 or GPT-3.5 to create human-readable topic labels.

## Connects To
- Relates to text embedding techniques covered in previous chapters.
- Connects to dimensionality reduction methods discussed earlier.
- Builds upon the clustering pipeline introduced in Chapter 13.