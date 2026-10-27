# Cheatsheet

### Cheatsheet: Large Language Models (LLMs) - Decision Tables, Comparison Matrices, and Quick Reference Rules  

---

#### **1. Setup and Platform Building**  
| **Action**                     | **Quick Reference Rule**                                                                 |
|-------------------------------|---------------------------------------------------------------------------------------|
| Choosing a Framework           | Use PyTorch or TensorFlow for flexibility and scalability.                              |
| Setting Up the Environment    | Install Python, Jupyter, and necessary libraries (e.g., transformers, datasets).         |

---

#### **2. Data Engineering**  
| **Action**                     | **Quick Reference Rule**                                                                 |
|-------------------------------|---------------------------------------------------------------------------------------|
| Data Collection               | Use web scraping, APIs, or surveys for structured/unstructured data.                  |
| Data Storage                 | Store in PostgreSQL, Hadoop, or cloud storage (e.g., AWS S3).                        |
| Data Processing              | Use Pandas, Dask, or PySpark for ETL workflows.                                     |

---

#### **3. Training Techniques**  
| **Action**                     | **Quick Reference Rule**                                                                 |
|-------------------------------|---------------------------------------------------------------------------------------|
| Model Architecture           | Choose between transformer-based (e.g., BERT) or simpler models for specific tasks.    |
| Training Strategy            | Use gradient descent with Adam optimizer and learning rate scheduling.                 |
| Overfitting Prevention       | Implement dropout, weight regularization, or early stopping.                          |

---

#### **4. Deployment Strategies**  
| **Action**                     | **Quick Reference Rule**                                                                 |
|-------------------------------|---------------------------------------------------------------------------------------|
| Model Serving                | Use Flask, FastAPI, or TensorFlow serving for APIs.                                   |
| Real-Time Inference          | Optimize models with quantization (e.g., TF-Quantize) or deploying on edge devices.    |

---

#### **5. Prompt Engineering**  
| **Action**                     | **Quick Reference Rule**                                                                 |
|-------------------------------|---------------------------------------------------------------------------------------|
| Crafting Prompts             | Use clear, concise, and specific prompts to guide model behavior.                      |
| Fine-Tuning Prompts          | Experiment with prompt engineering for improved outputs (e.g., "make this more conversational"). |

---

#### **6. Applications**  
| **Action**                     | **Quick Reference Rule**                                                                 |
|-------------------------------|---------------------------------------------------------------------------------------|
| Model Building Blocks         | Use pre-trained models as building blocks for custom applications.                    |
| API Development               | Create RESTful APIs or integrate with frameworks like FastAPI.                      |

---

#### **7. Deployment on Raspberry Pi**  
| **Action**                     | **Quick Reference Rule**                                                                 |
|-------------------------------|---------------------------------------------------------------------------------------|
| Hardware Setup               | Use Raspberry Pi Model 3 with sufficient RAM and storage.                              |
| Software Setup                | Install TensorFlow Lite or Hugging Face Transformers for inference.                   |
| Deployment Strategy          | Use microservices (e.g., Flask) for deployment on Pi.                                 |

---

#### **8. Production Challenges**  
| **Action**                     | **Quick Reference Rule**                                                                 |
|-------------------------------|---------------------------------------------------------------------------------------|
| Model Optimization           | Use model compression or quantization to reduce size and improve inference speed.       |
| Scalability                 | Deploy models in distributed systems (e.g., Kubernetes) for scalability.             |

---

### **Decision Tables: Choosing Between Tools/Methods**  

#### **Table 1: Data Storage Options**
| **Need**                     | **Recommendation**                                                                 |
|-------------------------------|-------------------------------------------------------------------------------------|
| Small datasets                | Use Pandas or Excel.                                                               |
| Large-scale, structured data  | Use PostgreSQL or Redshift.                                                        |
| Unstructured data            | Use Amazon S3 or Google Cloud Storage.                                            |

#### **Table 2: Training Frameworks**
| **Framework**               | **Use Case**                                                                 |
|-------------------------------|-----------------------------------------------------------------------------|
| PyTorch                      | Research and complex models.                                                   |
| TensorFlow                    | Production-ready models.                                                      |
| Hugging Face Transformers     | Pre-trained models for NLP tasks.                                                |

#### **Table 3: Deployment Platforms**
| **Need**                     | **Recommendation**                                                                 |
|-------------------------------|-------------------------------------------------------------------------------------|
| API Development               | Use Flask or FastAPI.                                                            |
| Real-time inference          | Use TensorFlow Serving or PyTorch Lightning.                                      |

---

### **Quick Reference Rules for Practitioners**  
1. Always start with a simple model before fine-tuning.  
2. Use prompts to guide LLM outputs but avoid over-engineering them.  
3. For deployment on edge devices, consider using TensorFlow Lite.  
4. Regularly evaluate and optimize your data pipeline.  

---

This cheatsheet provides a concise overview of key concepts, tools, and best practices for working with large language models.