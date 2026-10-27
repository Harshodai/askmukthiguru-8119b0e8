# Chapter 7: Prompt engineering: Becoming an LLM whisperer

## Core Idea
The single most important thing this chapter teaches is that prompt engineering is a powerful technique for achieving specific tasks with large language models (LLMs) without extensive training, fine-tuning, or tuning.

## Frameworks Introduced
- **Fine Tuning your Existing Models**: Adjusts an LLM's parameters to improve performance on a specific task.  
  - When to use: When you have a trained model and want to enhance its capabilities for a specific domain.
  - How: Fine-tune the model using prompts tailored to that domain.

- **One-Shot and Few-Shot prompting**: Provides instructions or examples directly to an LLM to generate responses without extensive training.  
  - When to use: When you need quick, context-specific answers from an LLM without additional training.
  - How: Use specific prompts with "one-shot" or "few-shot" templates.

- **Context Windowing**: Uses external knowledge sources (e.g., Wikipedia) to augment prompts and provide relevant context.  
  - When to use: When you need domain-specific information that isn't contained in the prompt itself.
  - How: Add RAG or database lookups to prompts to retrieve additional context.

- **Prompt Hyperparameter Tuning**: Modifies prompt engineering rules (temperature, top_p) to optimize results for specific tasks.  
  - When to use: When you need consistent and high-quality outputs from an LLM across multiple tasks.
  - How: Adjust hyperparameters based on empirical testing or feedback loops.

## Key Concepts
- **Prompt Engineering**: The process of crafting prompts that guide LLMs to perform specific tasks effectively.  
- **Five Whys**: A troubleshooting technique for understanding root causes by asking "Why" iteratively.  
- **Fine-Tuning**: Modifying an LLM's training data or hyperparameters to improve performance on a specific task.

## Mental Models
- Use Fine Tuning when you have a trained model and want to enhance its capabilities in a specific domain.
- Think of One-Shot prompting as providing direct instructions for an LLM to follow.
- Consider Context Windowing when you need domain-specific information that isn't contained within the prompt itself.

## Anti-patterns
- **Overfitting**: When prompts are too tailored to specific examples, leading to poor generalization.  
  - Why it fails: Prompts become brittle and fail on variations or new inputs.

## Code Examples
```python
from langchain import LlamaCpp
from langchain.prompts import PromptTemplate

llm = LlamaCpp(model="tiiuae/falcon-3b")
template = """ Tell me a story about {context} using the following tools:
- {tools[0]}
- {tools[1]}"""

# Example prompt engineering for summarizing news articles
context = "The article discussed the impact of renewable energy on modern society."
tools = [
    {"name": "Summary", "model": "summarize"},
    {"name": "Explain", "model": "explain"}
]
lm = falcon + "Once upon a time, there was a little engine that didn't have any tools. One day, it learned to use a calculator over the internet."
print(lm + template.format(
    context=context,
    tools=tools
))
```

## Reference Tables
| Technique                | Description                                                                 |
|--------------------------|-----------------------------------------------------------------------------|
| Fine Tuning               | Adjusts an LLM's parameters for specific tasks.                              |
| One-Shot Few-Shot       | Provides direct instructions or examples to generate responses.              |
| Context Windowing        | Uses external knowledge sources to augment prompts.                          |
| Prompt Hyperparameter    | Modifies prompt engineering rules (temperature, top_p) to optimize results.     |

## Key Takeaways
1. Understand the principles of prompt engineering and how it can be applied practically.
2. Learn when to use techniques like fine-tuning, one-shot prompting, and context windowing.
3. Avoid common pitfalls such as overfitting in your prompt engineering.

## Connects To
- Previous chapters on fine-tuning LLMs and context windowing provide foundational knowledge for this chapter's content.