# Cheatsheet

### Cheatsheet: Decision Tables, Comparison Matrices, and Quick Reference Rules for Language Models (LLMs)

---

#### **Decision Table: Choosing the Right LLM**
| **Scenario**                     | **Recommendation**                                                                 |
|-----------------------------------|-------------------------------------------------------------------------------------|
| Small-scale research              | Use smaller models like GPT-2 or Alpaca.                                            |
| Large-scale generation            | Use larger models like LLaMA or Falcon.                                           |
| Fine-tuning for specific tasks     | Use fine-tuned versions of base models (e.g., Flamingo, Mistral).                  |
| Deployment in production          | Use enterprise-grade models with deployment tools and monitoring.                 |

---

#### **Comparison Matrix: LLM Features**
| **Feature**                      | **GPT-4**                          | **Falcon 7B**                        | **Alpaca**                           |
|-----------------------------------|------------------------------------|---------------------------------------|--------------------------------------|
| Parameters                       | 50B parameters                     | 1.2B parameters                       | ~36M parameters                      |
| Generation speed                  | Slow                               | Moderate                              | Fast                                 |
| Context length                    | Long (512 tokens)                   | Shorter (256 tokens)                   | Long                                |
| Specialized tasks                | General-purpose                   | Specialized (math, code)              | General-purpose                     |
| Deployment cost                   | High                              | Moderate                             | Low                                  |

---

#### **Quick Reference Rules for LLMs**
1. Always start with a prompt that clearly defines the task.
2. Use precise and specific instructions to guide the model.
3. For generation tasks, set a reasonable temperature (0.7-0.9).
4. Monitor for hallucinations in large models like LLaMA.
5. Use error handling techniques like validators and output parsers.

---

#### **Decision Table: Retrieval vs. Generation**
| **Use Case**                     | **Retrieval Models**               | **Generation Models**                |
|------------------------------------|-----------------------------------|--------------------------------------|
| Information extraction           | Use VectorIndexRetriever          | Use generation models (e.g., GPT-4)  |
| Summarization                    | Use Retrieval-Augmented Generative AI| Use Generation AI                   |
| Question answering               | Use Retrieval Models             | Use Generation Models                |

---

#### **Comparison Matrix: Error Handling vs. Model Management**
| **Metric**                      | **Error Handling**                  | **Model Management**                 |
|-----------------------------------|------------------------------------|--------------------------------------|
| Efficiency                       | Focus on validation and output parsers | Focus on fine-tuning, pruning, and deployment  |
| Cost                              | Low                                | High                                 |
| Time                              | Moderate                           | Long                                  |

---

#### **Quick Reference Rules for Deployment**
1. Always install required libraries (e.g., LangChain, transformers) before starting.
2. Mount Google Drive in Colab using `mount('drive')`.
3. Use datasets with consistent formatting and structure.
4. Monitor model performance during deployment.

---

This cheatsheet provides a concise reference for practitioners working with LLMs, covering key aspects of their development, deployment, and management.