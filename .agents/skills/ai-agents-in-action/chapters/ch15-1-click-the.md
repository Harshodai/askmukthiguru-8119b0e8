```markdown
# Chapter 15: Employing Evaluation Techniques in Agent Reasoning and Prompt Flow

## Core Idea
The chapter emphasizes the importance of evaluating prompt flows to ensure consistent and reliable outputs. It introduces techniques like self-consistency evaluation and tree-of-thought prompting to enhance answer reliability, particularly for complex problems.

## Frameworks Introduced
- **Evaluation Flow**: A structured approach to validate and aggregate responses from LLMs.
  - When to use: When generating answers requires consistency across multiple runs or sources.
  - How: By integrating tools that calculate similarity metrics and determine the most consistent output.

## Key Concepts
- **Consistency Check**: Evaluating outputs based on semantic similarity to ensure reliability.
- **Tree-of-Thought Prompting (ToT)**: A method that breaks down reasoning into a tree structure, evaluating each step for better answer accuracy.

## Mental Models
- Use self-consistency evaluation when you need reliable answers across multiple runs or sources. Think of it as validating the output through similarity metrics to ensure consistency.
- Avoid relying solely on single-run outputs without validation, as they may not capture the full reasoning process.

## Anti-patterns
- **Lack of Thorough Evaluation**: Using prompt flows without validation can lead to inconsistent answers due to missing checks in the evaluation process.

## Code Examples
```python
from promptflow import tool
from typing import List
import numpy as np
from scipy.spatial.distance import cosine

@tool
def consistency(texts: List[str],
                embeddings: List[List[float]]) -> str:
    if len(embeddings) != len(texts):
        raise ValueError("The number of embeddings must match the number of texts.")
    mean_embedding = np.mean(embeddings, axis=0)
    similarities = [1 - cosine(embedding, mean_embedding) for embedding in embeddings]
    most_similar_index = np.argmax(similarities)
    from promptflow import log_metric
    log_metric(key="highest_ranked_output", value=texts[most_similar_index])
    return texts[most_similar_index]
```
This code demonstrates a tool function that calculates cosine similarity between embeddings to determine the most consistent answer.

## Reference Tables

| Evaluation Method          | Complexity | Effectiveness for Complex Problems |
|----------------------------|-------------|--------------------------------------|
| Self-Consistency Check     | Moderate    | High                                 |
| Tree-of-Thought Prompting  | High        | Very high                            |

## Key Takeaways
1. Use self-consistency evaluation to validate outputs across multiple runs or sources.
2. Implement tree-of-thought prompting for structured reasoning and improved answer accuracy.
3. Avoid relying solely on single-run outputs without validation.

## Connects To
- Relates to chapters on prompt engineering and agent decision-making processes.
```