# Chapter VI: Prompting with LangChain

## Core Idea  
LangChain provides multiple prompt types (System, Human, Chatbot) to control interactions, ensuring models respond appropriately for different contexts.

## Frameworks Introduced  
- **System Prompt**:  
  - When to use: Define system-level rules or behaviors.  
  - How: Use `langchain_community/gptq/system_prompt` template with specific instructions like "Act as a helpful assistant."

- **Human Prompt**:  
  - When to use: Guide interactions by providing context, examples, or instructions.  
  - How: Utilize `langchain_community/gptq/human_prompt` and customize it for tasks like summarization.

- **Chatbot Prompt**:  
  - When to use: Control responses in chatbots by setting ground rules or response styles.  
  - How: Implement `langchain_community/gptq/chatbot_prompt` with parameters such as "max_tokens" and "temperature."

## Key Concepts  
- **Prompt**: A directive used to influence model behavior, specifying the task, context, or interaction type.

## Mental Models  
Use System prompts when you need strict adherence to rules. Think of Human prompts as tools for guiding interactions. Chatbot prompts are for establishing consistent response patterns.

## Anti-patterns  
- **Ignoring Prompt Types**: Avoid using generic prompts without considering their specific use cases.  
  - Why it fails: Leads to unpredictable or irrelevant responses.

## Code Examples  
```python
from langchain_community.gptq import system_prompt, human_prompt, chatbot_prompt

# Example System Prompt
system_prompt template="Act as a helpful assistant and provide detailed explanations for all answers."
```

This demonstrates how to create a system prompt with specific instructions.

## Reference Tables  

| **Prompt Type** | **Use Case** | **Example Code** |
|------------------|--------------|------------------|
| System Prompt     | Define rules  | `langchain_community/gptq/system_prompt` |
| Human Prompt      | Guide context | `langchain_community/gptq/human_prompt` |
| Chatbot Prompt    | Control style | `langchain_community/gptq/chatbot_prompt` |

## Key Takeaways  
1. Use system prompts for strict rule adherence.  
2. Leverage human prompts to guide interactions with specific instructions.  
3. Implement chatbot prompts to control response styles and formats.

## Connects To  
- Relates to Chapter VII: Retrieval-Augmented Generation (for enhanced interaction techniques).  
- Connects to Chapter IX: Agents (for autonomous AI agents using these prompting methods).