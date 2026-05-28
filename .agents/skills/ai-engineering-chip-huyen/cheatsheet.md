# Cheatsheet

### Cheatsheet: Model Development and Optimization  

---

#### **Decision Table: Choosing a Foundation Model**  
| **Criteria**                | **Options**                                                                 |
|----------------------------|-----------------------------------------------------------------------------|
| **Accuracy vs. Cost**        | - Small dataset: Simpler models (e.g., linear regression) may suffice.<br>- Large dataset: Complex models (e.g., deep learning).<br>- Budget constraints: Prioritize simpler models first. |
| **Model Complexity**         | - Simple models: Faster deployment, lower resource usage.<br>- Complex models: Higher accuracy but require more resources. |
| **Deployment Requirements**  | - Real-time inference: Opt for lightweight models (e.g., pre-trained transformers).<br>- Batch processing: Full models may be acceptable. |

---

#### **Comparison Matrix: Optimization Techniques**  
| **Technique**               | **Advantages**                                                                 | **Disadvantages**                                                                 |
|----------------------------|---------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| Data Deduplication (Ch8)    | - Reduces dataset size, improves model training efficiency.<br>- Minimizes redundancy. | - May lose important information or context.                                  |
| Model Distillation (Ch23)   | - Produces smaller models that mimic large models' behavior.<br>- Reduces computational overhead. | - May sacrifice some accuracy.                                                  |

---

#### **Quick Reference Rules for Practitioners**  
1. **Improving Model Accuracy**: Prioritize optimization techniques only when additional accuracy is critical (e.g., from 90% to 95%).<br>Rule of thumb: Evaluate the cost-benefit trade-off before investing in advanced optimization methods.

2. **Inference Optimization**:  
   - If real-time inference is required, use lightweight models or employ quantization.<br>
   - For batch processing, full models may be acceptable without significant performance degradation.

3. **Model Monitoring (Ch13)**:  
   - Use automated monitoring tools to track model performance and detect drift.<br>
   - Schedule periodic manual reviews for critical applications.

4. **Semantic Similarity**:  
   - Apply semantic similarity measures when dealing with noisy or ambiguous data.<br>
   - Exact matching is preferred when data quality is high and noise levels are low.

---

This cheatsheet provides a concise reference for practitioners to make informed decisions in model development, optimization, and deployment.