# Cheatsheet

### Cheatsheet: Decision Tables, Comparison Matrices, and Quick Reference Rules for Large Language Models (LLMs)

---

#### **Decision Table 1: Choosing the Right LLM Architecture**
| **Use Case**                     | **Recommendation**                                                                 |
|------------------------------------|-----------------------------------------------------------------------------------|
| **Text Generation**               | Transformer-based models (e.g., GPT) are ideal due to their efficiency and flexibility. |
| **Classification/Clustering**    | Use pre-trained language models fine-tuned for classification tasks.             |
| **Extraction of Features**        | Pre-trained models can extract features without additional training.              |
| **Translation or Summarization**| Transformer-based models are effective for these tasks, especially with appropriate tokenization. |

---

#### **Comparison Matrix: Performance vs. Use Cases**
| **Metric**                     | **Generative Models (e.g., GPT)**                                           | **Discriminative Models (e.g., BERT)**                                      |
|----------------------------------|---------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| **Speed**                       | Faster inference due to simpler architecture.                                  | Slower but more accurate due to complex reasoning.                            |
| **Memory Usage**                | Lower, suitable for resource-constrained environments.                         | Higher memory usage, better for tasks requiring context and depth.             |
| **Training Time**               | Longer with large datasets.                                                   | Shorter training time compared to generative models.                          |
| **Use Cases**                   | Text generation, summarization, creative writing.                              | Question answering, text classification, sentiment analysis.                    |

---

#### **Quick Reference Rules for LLM Development**
1. **Understanding Large Language Models (Ch. 1)**:
   - Use pre-trained models as a starting point to save time and resources.
   - Familiarize yourself with the basics of neural networks and attention mechanisms.

2. **Working with Text Data (Ch. 2)**:
   - Normalize text by converting it to lowercase, removing punctuation, and handling rare words.
   - Use tokenization libraries like `tokenize` or `nltk` for efficient processing.

3. **Coding Attention Mechanisms (Ch. 3)**:
   - Start with the dot product attention mechanism before moving to scaled dot-product attention.
   - Implement multi-head attention to capture diverse contextual representations.

4. **Implementing GPT from Scratch (Ch. 4)**:
   - Use PyTorch or TensorFlow for implementation due to their flexibility and active community support.
   - Optimize hyperparameters such as learning rate, batch size, and number of layers.

5. **Pretraining on Unlabeled Data (Ch. 5)**:
   - Implement masked language modeling objective function using cross-entropy loss.
   - Be cautious with memory constraints when training large models; use techniques like gradient checkpointing.

6. **Fine-tuning for Classification (Ch. 6)**:
   - Adjust learning rates and dropout layers to prevent overfitting during fine-tuning.
   - Monitor validation performance to select the best model variant.

7. **Fine-tuning for Instructions (Ch. 7)**:
   - Engineer effective prompts that clearly guide the model's behavior.
   - Consider integrating instruction-following mechanisms into pre-trained models for specific tasks.

---

This cheatsheet provides a concise reference for practitioners working with large language models, covering key concepts, architectures, and practical implementation tips.