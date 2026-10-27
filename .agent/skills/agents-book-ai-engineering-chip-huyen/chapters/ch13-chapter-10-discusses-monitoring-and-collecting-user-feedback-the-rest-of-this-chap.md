# Chapter 13: Model Build Versus Buy  

## Core Idea  
The chapter emphasizes that using commercial model APIs can significantly reduce the number of candidate models compared to hosting open source models yourself.  

## Frameworks Introduced  
- **Model Build Versus Buy Framework**:  
  - When to use: Decide whether to use pre-trained models (APIs) or host your own trained models, considering factors like data ownership, restrictions, and evaluation needs.  
  - How: Compare the pros and cons of model APIs versus hosting open source models, including licensing, data usage, and commercial implications.  

## Key Concepts  
- **Open Source Model**: A model whose weights are publicly available but may lack access to training data or have restrictive licenses.  
- **Model License**: The legal terms governing the use, modification, and distribution of a model, which can impact its retraining and adaptation.  
- **Model API**: An interface that hosts and runs models for users to interact with, often exposing features like evaluation tools and datasets.  
- **Evaluation Pipeline**: A custom process for assessing model performance using prompts and metrics tailored to specific needs.  
- **Public Benchmark**: A dataset or platform used to evaluate AI systems, which may not always be reliable due to potential biases or inaccuracies.  

## Mental Models  
- Use model APIs when you want fewer candidate models but need access to pre-trained weights. Think of it as a black box that provides ready-to-use capabilities without the overhead of hosting and maintaining your own model.  

## Anti-patterns  
- **Avoid using open source models for proprietary data**: This can lead to legal issues or violations of terms of use, especially if the data isn’t publicly available.  

## Code Examples  
```python
def evaluate_model(model_api):
    """Evaluates a model API based on specific criteria."""
    criteria = {
        "commercial_use": False,
        "data_openness": True,
        "license_restrictions": False
    }
    
    if criteria["commercial_use"]:
        return " commercial use restrictions apply."
    
    if not criteria["data_openness"]:
        return " cannot access training data."
    
    if criteria["license_restrictions"]:
        return " restricted by licensing terms."
    
    return "Model API passes all criteria for evaluation."
```

## Reference Tables  
| Model Type         | Data Usage       | Commercial Use | License Restrictions |  
|--------------------|------------------|-----------------|-----------------------|  
| Open Source Models  | Limited          | N/A             | Varies                 |  
| Model APIs         | Full             | Yes (if applicable)| None or restricted    |  

## Key Takeaways  
1. Use model APIs when you need pre-trained models without the overhead of hosting your own.  
2. Be cautious about using open source models for proprietary data due to potential legal risks.  
3. Always evaluate model APIs based on commercial use, data access, and licensing terms before deployment.  

## Connects To  
- Relates to benchmarking practices (Chapter 10) and evaluation pipelines (Chapter 4).