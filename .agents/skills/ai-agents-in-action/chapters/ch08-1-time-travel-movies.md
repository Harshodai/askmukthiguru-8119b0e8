# Chapter 8: Semantic Kernel (SK) - Building Agents with Organized Actions

## Core Idea
The chapter introduces **Semantic Kernel (SK)**, a powerful framework for organizing and executing actions in intelligent agents. SK allows developers to define semantic functions (prompt templates) and native functions (code-based tasks), which can be registered as plugins. This approach simplifies task management, enhances organization, and integrates seamlessly with LLMs.

## Frameworks Introduced
- **Semantic Kernel (SK)**: 
  - When to use: Organizing multiple skills or actions in an agent.
  - How: SK provides a unified interface for defining, registering, and executing functions as plugins or native tasks.

## Key Concepts
- **Semantic Function**: A prompt template with placeholders that can be filled by input variables. It defines the interaction pattern between the LLM and the user.
- **Native Function**: Encapsulates code to perform specific tasks (e.g., web scraping, API calls).
- **Kernel**: The orchestrator that manages plugins and executes function calls.

## Mental Models
- Use SK when you need to manage multiple skills or actions in an agent. Think of SK as a tool that organizes these functions into a cohesive system.
- Use native functions for code-based tasks and semantic functions for prompt-based interactions, ensuring clear separation of concerns.

## Anti-patterns
- **Avoid monolithic codebases**: Instead of handling everything within one function, distribute responsibilities among plugins to improve maintainability and scalability.
- **Avoid overcomplicating function calls**: Do not use unnecessary models or complex setups when a simple solution suffices. Stick to the minimum required for each task.

## Code Examples
```python
# SK_connecting.py

import semantic_kernel as sk
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion

selected_service = "OpenAI"
kernel = sk.Kernel()
service_id = None

if selected_service == "OpenAI":
    api_key, org_id = sk.openai_settings_from_dot_env()
    service_id = "oai_chat_gpt"
    kernel.add_service(
        OpenAIChatCompletion(
            service_id=service_id,
            ai_model_id="gpt-3.5-turbo-1106",
            api_key=api_key,
            org_id=org_id,
        )
    )

async def run_prompt(prompt):
    result = await kernel.invoke_prompt(prompt)
    return result

# Use asyncio.run to execute the async function
asyncio.run(run_prompt("recommend a movie about time travel"))
```

This code demonstrates how to set up SK, add an OpenAI service, and invoke a prompt asynchronously.

## Reference Tables
| **Term**          | **Definition**                                                                 |
|-------------------|-----------------------------------------------------------------------------|
| Semantic Kernel (SK) | A framework for organizing actions (functions) as plugins or native tasks. |
| Semantic Function  | A prompt template with placeholders that can be filled by input variables.   |
| Native Function    | Encapsulates code to perform specific tasks, such as web scraping or API calls. |

## Key Takeaways
1. Use SK when you need to manage multiple skills or actions in an agent.
2. Define semantic functions for prompt-based interactions and native functions for code-based tasks.
3. Organize your plugins and functions within the SK kernel for better maintainability.

This chapter connects to earlier concepts about building technical books and integrating AI tools like OpenAI into applications. It also sets up future sections on advanced SK functionalities, such as organizing skills by context variables or using SK's built-in features for efficient function management.