# Cheatsheet

### Cheatsheet for Large Language Models and Related Topics  

---

#### **Decision Table: When to Use Certain Components**  
| **Component**          | **Use Case**                                                                 | **Example Model/Technique**                     |
|------------------------|-----------------------------------------------------------------------------|-----------------------------------------------|
| Input Embedding         | Convert raw text into dense vectors for processing.                    | BERT, RoBERTa, GPT-3 (Chapters 1, 3)           |
| Positional Encoding     | Encode positional information in sequences.                              | Used in BERT and GPT models (Chapters 2, 4)      |
| Decoder in Action       | Generate text based on input embeddings.                                  | Beam search decoding (Chapter 5)                 |
| Encoder Models          | Process input to extract features.                                        | Encoder-only models like BERT (Chapters 6, 9)     |
| Tokenize Documents      | Convert text into tokens for model processing.                            | BERT tokenization (Chapter 7)                   |
| Semantic Search         | Retrieve similar documents or texts without LLMs.                        | FAISS-based search systems                    |
| Retrieval Augmented Generation (RAG)| Combine retrieval with generation to enhance search results.        | RAG models using dense and sparse retrieval (Chapters 13, 14) |

---

#### **Comparison Matrix: Model Features**  
| **Feature**              | **BERT**                     | **GPT-3**                    | **RAG Models**                 |
|--------------------------|-------------------------------|-------------------------------|-------------------------------|
| Speed                   | Faster training and inference.   | Slower but more accurate.      | Depends on retrieval speed.    |
| Accuracy                | High for text classification.  | State-of-the-art in NLP tasks. | May trade-off with retrieval accuracy. |
| Use Cases              | Pre-trained for specific tasks. | General language understanding.| Tasks requiring retrieval+generation. |

---

#### **Quick Reference Rules**  
1. **BERT Processing Pipeline**: Always start with tokenization and positional encoding before feeding into the decoder.
2. **Decoder Activation**: Use beam search decoding when generating text from BERT or GPT models.
3. **Encoder-Decoder Trade-off**: Encoder-only models are faster but may lack context handling; decoder-only models generate more accurate outputs.
4. **RAG Workflow**: Preprocess documents with a retrieval system, encode queries and passages, and use dense/sparse retrieval for efficient search.

---

This cheatsheet provides a concise reference to key concepts and techniques in large language models and related areas, helping practitioners quickly navigate the material covered in the chapters.