# Chapter 50: Open source LLMs

## Core Idea
The chapter explores various open-source large language models (LLMs) available for local execution, highlighting their types, performance metrics, and best practices for deployment.

## Frameworks Introduced
- **Open-Source LLM**: An LLM trained on public datasets, ideal for research or experimentation.
  - When to use: Choose this when you need a model without proprietary data or resources.
  - How: Clone the model repository, fine-tune if necessary, and deploy locally.

## Key Concepts
- **Instruct-tuned Model**: An LLM optimized for following instructions or answering questions.
- **Code Generation Model**: Designed to generate, explain, or debug code snippets.
- **Domain-specific Model**: Tailored for specific industries or tasks like mathematics or healthcare.
- **Foundation Model**: A general-purpose model trained on diverse data.

## Mental Models
- Use an Instruct-tuned model when you need reliable responses to user queries.  
- Think of Code Generation models as tools for automated debugging and code generation.

## Anti-patterns
- **Avoid using a Domain-specific model for general tasks** because it may lack the necessary knowledge or flexibility.
  - Why it fails: It risks providing irrelevant or incorrect information when not suited for the task.

## Code Examples
```python
# Example of cloning an LLM repository and running locally
!git clone https://huggingface.co/username/repository.git
cd repository
# Fine-tune if necessary
# Run the model using lm-studio or ollama
```

This demonstrates how to set up and run an open-source LLM locally.

## Reference Tables

| Model Type          | Example Models                  | Key Metrics               |
|---------------------|---------------------------------|---------------------------|
| Foundation         | DeepSeek-V3, Mistral-7B-v0.3 | Size: 671M Parameters     |
| Instruct-tuned      | Qwen2.5-72B-Instruct           | IFEval: 86.38%            |
| Code Generation     | Qwen2.5-Math-7B               | MATH-L5: 30.51%           |
| Domain-specific     | Llama-3.3-70B-Instruct         | GPQA: 48.13%              |

## Key Takeaways
1. Choose the right model type based on your specific task (e.g., Instruct for QA tasks).
2. Always validate data quality before training to ensure reliable outputs.
3. Be aware of a model's limitations and ethical considerations.

## Connects To
- Relates to chapters on model selection, deployment, and ethical AI practices.