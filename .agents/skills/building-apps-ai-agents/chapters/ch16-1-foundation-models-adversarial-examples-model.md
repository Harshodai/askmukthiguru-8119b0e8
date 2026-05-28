```markdown
# Chapter 16: Protecting Agentic Systems

## Core Idea
The chapter emphasizes the critical importance of securing foundation models, data handling practices, and agent systems to mitigate adversarial threats, vulnerabilities, and internal failures.

## Frameworks Introduced
- **Model Evasion Attacks**: Exploitation through evasion techniques such as parameter substitution or image forgery.
  - When to use: To identify and defend against model manipulation by adversaries.
  - How: Implement robust detection mechanisms like input validation and adversarial training.

## Key Concepts
- **Adversarial Examples**: Inputs crafted to deceive AI models, often used in evasion attacks.
- **Defensive Techniques**: Includes defensive training (e.g., data augmentation), robust architectures, and anomaly detection systems.

## Mental Models
Use model inversion when attempting to manipulate foundation models. This technique involves querying the model to understand its decision-making process for specific outputs.

## Anti-patterns
- **Overfitting Models**: Exploitation of adversarial examples can lead to overfitted models that fail under real-world conditions.
  - Why it fails: Overfitting reduces a model's generalizability, making it vulnerable to adversarial attacks.

## Code Examples
```python
# Example code for defensive training using data augmentation
from sklearn.preprocessing import ImageEnhance

def augment_image(image):
    enhancer = ImageEnhance(image)
    # Apply random brightness and contrast adjustments
    adjusted = enhancer.enhance([1.2, 1.3])
    return adjusted
```

- **What it demonstrates**: Application of data augmentation to improve model robustness against adversarial attacks.

## Reference Tables
| Metric                | Value       |
|-----------------------|------------|
| AES Key Size          | 256 bits   |
| Merkle Tree Depth     | Variable   |

## Key Takeaways
1. Implement defensive training and robust architectures to counteract adversarial examples.
2. Use encryption, provenance tracking, and integrity checks for secure data handling.
3. Apply RBAC principles to enforce role-based access control in agent systems.

## Connects To
- Data security practices (Chapter 15)
- Model robustness techniques (Chapter 14)