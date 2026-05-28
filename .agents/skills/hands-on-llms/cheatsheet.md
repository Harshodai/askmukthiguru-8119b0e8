# Cheatsheet

### Cheatsheet: Decision Tables, Comparison Matrices, and Quick Reference Rules for Practitioners

---

#### **Decision Table: Choosing the Right Technique**
| **Use Case**                     | **Recommended Technique**              | **Key Considerations**                                                                 |
|-----------------------------------|----------------------------------------|---------------------------------------------------------------------------------------|
| Text Preprocessing                | Tokenization (Chapter 2)               | Ensure consistent tokenization and handling of special characters.                 |
| Dimensionality Reduction          | Text Embedding (Chapters 14, 26)       | Use pre-trained embeddings or fine-tune models for specific tasks.                  |
| Clustering                       | Text Clustering (Chapters 5, 13)        | Leverage clustering algorithms like k-means or LDA for grouping similar texts.     |
| Classification                   | Text Classification (Chapters 8, 12)      | Use supervised learning models with appropriate feature engineering.               |
| Search and Retrieval             | Semantic Search (Chapters 7, 17)        | Implement vector search using embeddings or similarity measures.                   |
| Generation                      | Prompt Engineering (Chapters 15, 23)    | Design effective prompts to guide AI outputs for specific tasks.                    |

---

#### **Comparison Matrix: Classification vs. Clustering**
| **Aspect**                     | **Classification**                  | **Clustering**                     |
|---------------------------------|-------------------------------------|------------------------------------|
| **Objective**                   | Predict class labels               | Group similar data points           |
| **Supervision**                 | Labeled data required             | Unlabeled data used                |
| **Output**                      | Classes or categories              | Clusters                           |
| **Use Case**                   | Spam detection, sentiment analysis    | Document categorization, topic modeling |

---

#### **Quick Reference Rules for Practitioners**
1. **Text Preprocessing**: Always perform tokenization and lemmatization before applying machine learning models.
2. **Embedding Models**: Use pre-trained models (e.g., BERT) unless fine-tuning is necessary for specific tasks.
3. **Clustering**: Evaluate the number of clusters using metrics like silhouette score or elbow method.
4. **Relevance Scoring**: Apply TF-IDF or BM25 algorithms to measure document relevance.
5. **Prompt Engineering**: Tailor prompts to guide AI outputs effectively, especially in generative tasks.
6. **Fine-Tuning**: Always validate models on unseen data post-fine-tuning to ensure generalization.

---

This cheatsheet provides a concise reference for practitioners working with text data, focusing on preprocessing, classification, clustering, and retrieval techniques.