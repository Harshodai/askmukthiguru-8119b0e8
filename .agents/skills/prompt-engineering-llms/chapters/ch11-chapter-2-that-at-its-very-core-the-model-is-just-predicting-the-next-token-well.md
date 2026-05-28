# Chapter 8: Conversational Agency

## Core Idea
This chapter teaches how to build conversational agents that leverage large language models (LLMs) for task-based interactions by structuring prompts, managing context, and enabling tool usage.

### Frameworks Introduced
- **Prompt Engineering Approach**: Uses system messages, tool definitions, and artifact management.
  - When to use: To structure conversations around specific tasks or tools.
  - How: Define a system message that sets the tone for interactions, outline tool definitions with arguments, and organize artifacts (evidence) from prior exchanges.

- **Chain-of-Thought Prompting**: Encourages the model to reason step-by-step by presenting its thought process in a narrative format.
  - When to use: To improve reasoning about complex tasks or decisions.
  - How: Ask the model to explain its thinking process in detail, allowing it to build on previous steps.

- **ReAct Model**: Focuses on structured task-based interactions with tools and artifacts.
  - When to use: For complex multi-step tasks requiring tool coordination.
  - How: Define tasks with clear objectives, break them into subtasks, and provide tools and artifacts as directed.

### Key Concepts
- **Chain-of-Thought Prompting**: A method where the model explains its reasoning step-by-step within a single interaction.
- **ReAct Model**: A task-based framework that organizes interactions around predefined steps and artifacts.
- **Artifact Management**: The process of collecting, storing, and presenting information from prior exchanges to aid in current tasks.

### Mental Models
- Use prompt engineering when you need to structure conversations around specific tasks or tools.  
- Think of chain-of-thought prompting as a way to improve reasoning by breaking down complex tasks into smaller steps.
- Organize context effectively by prioritizing relevant artifacts and using them to guide the model's actions.

### Anti-patterns
- Overload the model with too many unrelated prompts without guiding it through structured interactions.  
- Rely solely on human interaction for task completion, ignoring the model's reasoning capabilities.  
- Ignore prior conversation or fail to extract enough information from artifacts when they are available.  
- Fail to organize context, leading to confusion and incomplete reasoning.

### Code Examples
```python
# Example of a tool definition in OpenAI's API
tool_name = "get_temperature"
toolDefinition = {
  "name": "get_temperature",
  "function": "get_temperature",
  "parameters": [],
  "context": None,
  "description": "Returns the current temperature in degrees Fahrenheit.",
  "arguments": []
}
```
This demonstrates how to define a tool for retrieving temperature data, which can be used by an LLM to assist with weather-related tasks.

### Reference Tables
| **Decision Matrix** | **Criteria** | **Action** |
|----------------------|--------------|------------|
| Context Clarity     | High         | Use chain-of-thought prompting |
| Reasoning Improvement | Moderate     | Implement structured prompts |

## Key Takeaways
1. Structure conversations with clear system messages and tool definitions.
2. Use chain-of-thought prompting to enhance reasoning about complex tasks.
3. Organize context by prioritizing relevant artifacts.
4. Empower users with tools that gather, process, and present information.

## Connects To
- Earlier concepts on prompt engineering (Chapter 5).
- Task modeling and tool usage from Chapter 6.