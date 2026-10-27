# Chapter 4: Building Systems with Large Language Models (LLMs)

## Core Idea
This chapter emphasizes the importance of understanding when and how to leverage LLMs for tasks such as classification, retrieval, and generation. It highlights the strengths and limitations of different model architectures and provides actionable guidance on selecting appropriate frameworks and techniques.

---

## Frameworks Introduced
- **OpenAI/GPT-4**: A proprietary large language model requiring significant computational resources.
  - When to use: For highly accurate and versatile tasks when access to expensive cloud infrastructure is available.
  - How: Requires a powerful GPU with sufficient VRAM (e.g., 16 GB) and may involve fine-tuning for specific applications.

- **Anthropic/Claude**: Another proprietary model designed for complex reasoning tasks.
  - When to use: For niche applications requiring human-like common sense or specialized knowledge.
  - How: Limited access due to high licensing costs, making it suitable for enterprise use cases.

- **Microsoft/Phi and Meta/Llama**: Open-source alternatives with varying performance characteristics.
  - When to use: For cost-effective solutions or when local deployment is preferred.
  - How: Requires minimal setup and can be fine-tuned for specific tasks without access to high-end hardware.

---

## Key Concepts
- **Unsupervised Learning**: LLMs are trained on vast amounts of unlabeled data, enabling tasks like classification and retrieval.
- **Pre-training vs. Fine-tuning**: Pre-trained models (e.g., BERT) capture general linguistic patterns, while fine-tuned models adapt to specific domains.
- **Context Window**: The number of tokens a model can process at once affects its performance in tasks requiring extended reasoning.

---

## Mental Models
Use LLMs when:
- You have abundant data but limited labeling capacity (e.g., for classification or retrieval).
- You need interpretable outputs for complex decisions (e.g., medical diagnosis).

Avoid over-reliance on LLMs without considering:
- The model's context window and its ability to handle out-of-distribution data.
- The ethical implications of using pre-trained models trained on biased datasets.

---

## Anti-patterns
- **Over-reliance on Proprietary Models**: Using closed-source LLMs for tasks where open-source alternatives are available can limit flexibility and customization.

---

## Code Examples
```python
from transformers import AutoModelForCausalLM, AutoTokenizer

model = AutoModelForCausalLM.from_pretrained(
    "microsoft/Phi-3-mini-4k-instruct",
    device_map="cuda",
    torch_dtype="auto",
    trust_remote_code=True,
)
tokenizer = AutoTokenizer.from_pretrained("microsoft/Phi-3-mini-4k-instruct")

generator = pipeline(
    "text-generation",
    model=model,
    tokenizer=tokenizer,
    return_full_text=False,
    max_new_tokens=500,
    do_sample=False
)

messages = [
    {"role": "user", "content": "Create a funny joke about chickens."}
]
output = generator(messages)
print(output[0]["generated_text"])
```

**What it demonstrates**: Using an open-source LLM (Phi-3-mini) with the transformers library to generate text, highlighting the ease of integration and deployment.

---

## Reference Tables
| Model      | VRAM Requirements | Performance |
|------------|-------------------|-------------|
| Microsoft/Phi | 6-16 GB            | High        |
| Meta/Llama | 4-8 GB             | Efficient   |

---

## Key Takeaways
1. Choose open-source models for flexibility and cost-effectiveness.
2. Use proprietary models when access to high-end hardware is feasible.
3. Always consider the model's context window and ethical implications.

---

## Connects To
- Chapter 1: Overview of LLM development and its impact on AI.
- Chapter 2: Tokenization and embeddings, foundational for LLM operations.
- Chapter 3: Language models and their underlying mechanisms.