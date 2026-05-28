# Cheatsheet

### Cheatsheet: Decision Tables, Comparison Matrices, and Quick Reference Rules  

#### **Decision Table for Model Selection**  
| **Criteria** | **Possible Choices** |  
|--------------|-----------------------|  
| **Model Complexity** | Simple (e.g., linear regression) |  
| **Accuracy** | High accuracy required? |  
| **Interpretability** | Must be interpretable? |  
| **Scalability** | Data is large? |  
| **Computational Resources** | Limited resources available? |  

---

#### **Comparison Matrix: Foundation Models vs. Large Language Models (LLMs)**  
| **Feature**               | **Foundation Models**                     | **Large Language Models (LLMs)**          |  
|---------------------------|------------------------------------------|------------------------------------------|  
| **Training Data**         | Small, diverse dataset                   | Massive, specialized datasets            |  
| **Task-Specificity**      | General-purpose tasks                    | Task-specific tasks                       |  
| **Size**                  | Smaller model size                      | Larger model size                        |  
| **Inference Time**        | Faster inference time                    | Slower inference time                     |  

---

#### **Quick Reference Rules for Practitioners**  

1. **Data Collection**  
   - Always ensure data is representative and unbiased.  
   - Use structured formats (e.g., CSV, JSON) for easy processing.  
   - Collect enough labeled data to train models effectively.  

2. **Model Evaluation**  
   - Use cross-validation to assess model performance.  
   - Metrics: Accuracy, precision, recall, F1-score, AUC-ROC.  
   - Always report confidence intervals for key metrics.  

3. **Bias and Fairness**  
   - Regularly check for bias in training data.  
   - Implement fairness metrics (e.g., demographic parity).  

4. **Continuous Learning**  
   - Retrain models periodically with new data.  
   - Monitor performance drift over time.  

5. **Deployment Best Practices**  
   - Use model interpretability tools (e.g., SHAP, LIME).  
   - Plan for cold-start periods in deployment.  

---

This cheatsheet provides a concise reference for practitioners to quickly access essential concepts and practices covered in the chapters.