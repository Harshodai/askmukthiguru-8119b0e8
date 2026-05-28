# Chapter IX: Agents

## Core Idea  
Large pre-trained models like LLMs enable the creation of intelligent agents by integrating tools and reasoning engines to plan and execute complex tasks.

## Frameworks Introduced  
- **LangChain**: A framework that simplifies building agents using a step-by-step execution model for tasks requiring sequential processing.  
  - When to use: For creating agents that require a series of actions in order.  
  - How: By defining tools, input formats, and output handling within the same request chain.  

- **LlamaIndex**: A framework designed for real-time data access using an inverted index structure.  
  - When to use: For agents needing immediate access to external data sources like APIs or databases.  
  - How: By creating a custom tool that accesses the index and returns results in a structured format.  

- **OpenAI's Assistants API**: A framework for building agents that interact with multiple tools, each handling specific tasks.  
  - When to use: For agents requiring access to various external tools or services.  
  - How: By creating custom tools for each external service and using the Assistant API to manage their execution.  

## Key Concepts  
- **Action Agents**: Agents that perform a single action in response to an input query, suitable for straightforward tasks.  
- **Plan-and-Execute Agents**: Agents that develop and execute plans with multiple actions, allowing for adaptability based on intermediary results.  
- **Tools**: Functions that achieve specific tasks, such as using the Google Search API or running code in a Python REPL.  
- **Reasoning Engine/Core**: The large model powering the agent's decision-making capabilities.  
- **Agent Orchestration**: The system managing interactions between the LLM and its tools to ensure smooth execution.

## Mental Models  
- Use LangChain when you need agents that require sequential task execution. Think of it as a pipeline for processing inputs through multiple steps.  

- Use LlamaIndex when you need agents that require real-time data access from external sources. Think of it as a tool that fetches and processes data on the fly.  

- Use OpenAI's Assistants API when you need agents that interact with multiple external tools or services. Think of it as a hub for managing various external functionalities.

## Anti-patterns  
- **Avoid monolithic architectures**: Avoid creating a single, complex system when a distributed approach would be more efficient and scalable.  

## Code Examples  
```python
from langchain.agents import Tool

# Define a tool to add two numbers
def add_numbers(a: int, b: int) -> int:
    return a + b

addTool = Tool(name="Add Numbers", func=add_numbers)

# Create an agent using the tool
@ lanchain.execute
async def my_agent(query: str) -> str:
    result = await query.addTool([addTool], parameters={"q": query})
    return f"The sum of the numbers is {result[0]['output']}"
```

This demonstrates how to create a simple agent using LangChain's tool execution model.

## Reference Tables  

| Framework | Use Case | Tools Involved | Access Type |
|----------|-----------|----------------|-------------|
| LangChain | Sequential tasks | Custom tools | API calls     |
| LlamaIndex | Real-time data | External APIs  | Real-time    |
| OpenAI's Assistants API | Multiple services | Custom tools | API calls     |

## Key Takeaways  
1. Use LangChain for agents requiring sequential task execution and step-by-step processing.  
2. Leverage LlamaIndex when you need real-time data access from external sources.  
3. Utilize OpenAI's Assistants API for agents interacting with multiple external tools or services.

## Connects To  
- Relates to the concept of toolchest in Chapter 48: Toolchest