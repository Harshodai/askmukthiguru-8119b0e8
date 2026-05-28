```markdown
# Chapter 4: Moving to Chat

## Core Idea
The chapter explains how to transform document completion models into robust chat interfaces by leveraging Reward Model Hyper-fine Tuning (RLHF) fine-tuning. This approach enables models to act like helpful, honest, and harmless AI assistants while maintaining their alignment with user expectations.

## Frameworks Introduced
- **ChatML Prompt Engineering**:  
  - When to use: When creating chat interfaces or integrating external APIs.
  - How: Involves crafting structured prompts with system messages that guide the model's behavior. The assistant's role is clearly defined, ensuring consistent and polite responses.

## Key Concepts
- **Prompt Engineering**: Tailoring prompts to control an AI's behavior by providing context and instructions in a specific format.
- **ChatML**: A markup language used to annotate chat conversations, ensuring predictable and controllable interactions between users and AI assistants.
- **RLHF Fine-Tuning**: A technique that fine-tunes LLMs to follow user preferences by training them on human-annotated helpfulness scores.

## Mental Models
- Use ChatML when you need structured prompts for chat interfaces. This ensures consistent behavior and avoids unintended outcomes like monotony or politeness.
  - Think of ChatML as a framework for creating predictable and polite interactions between users and AI assistants.

## Anti-patterns
- **Avoid losing alignment**: Fine-tuning models too aggressively can reduce their ability to handle diverse tasks, leading to less effective performance in specific domains.

## Code Examples
```python
from openai import OpenAI

client = OpenAI()
response = client.ChatCompletion.create(
  model="gpt-4o",
  messages=[
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What is the capital of France?"},
    {"role": "assistant", "content": "The capital of France is Paris."}
  ],
  temperature=0.0
)
```
- **What it demonstrates**: Fine-tuning an LLM to provide helpful and accurate responses by controlling its prompt engineering with ChatML.

## Reference Tables
| Parameter        | Purpose                          |
|------------------|-----------------------------------|
| `messages`       | List of chat messages              |
| `role`           | Message role (system, user, assistant)|
| `temperature`    | Controls response creativity      |

## Key Takeaways
1. Use ChatML to create structured prompts that guide AI behavior.
2. Fine-tune models with RLHF to align with user preferences.
3. Preserve alignment while adding chat-specific features.

## Connects To
- Previous discussions on document completion and prompt engineering concepts.
```