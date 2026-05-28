# Chapter 34: Building tool-based agents with LangGraph

## Core Idea
This chapter teaches how to build intelligent agents that combine semantic search capabilities with multiple external tools (e.g., weather APIs) to provide dynamic, context-aware recommendations. The approach leverages the LangGraph framework to orchestrate tool usage and maintain a coherent knowledge base.

## Frameworks Introduced
- **LLM Node**: Manages tool execution by deciding which tools to call based on user queries.  
  - When to use: When building agents that require flexible tool chaining and dynamic information retrieval.
  - How: It evaluates the LLM's responses, identifies relevant tools, and executes them as needed.

- **ReAct Agent**: A high-level abstraction of the LLM node, simplifying agent construction while maintaining reliable tool orchestration.  
  - When to use: For rapid development and deployment of agents with prebuilt LangGraph support.
  - How: Automates the interaction flow, handling tool calls and response synthesis internally.

## Key Concepts
- **Vector Store**: A database storing structured data (e.g., Cornwall beach locations) for semantic search.  
  - Used to fetch relevant information when no direct tool results are available.

- **Tool Execution Node**: Handles tool invocation by parsing query arguments and formatting responses.  
  - Ensures tools are only called with valid parameters and organizes results for coherent output.

- **System Message**: A prompt added to LLM requests that guides the assistant's behavior (e.g., limiting hallucinations).  
  - Encourages reliability and accuracy in tool usage by providing explicit instructions.

## Mental Models
- The "LLM as Oracle" model: The LLM provides context-aware responses while tools handle execution.  
  - Think of it as combining a powerful search engine with multiple specialized tools for specific tasks.

- The "ReAct Chain" model: Breaking down complex queries into sequential tool calls, ensuring each step builds on the previous result.  
  - Simplifies agent development by abstracting low-level orchestration details.

## Anti-patterns
- **Over-reliance on manual tool binding**: Without proper guidance or system messages, tools may be invoked incorrectly.  
  - Solution: Use predefined tool descriptions and system prompts to ensure accurate execution.

- **Neglecting user feedback**: Agents that provide irrelevant or incomplete results fail to build trust.  
  - Solution: Implement a feedback loop where users refine queries based on previous interactions.

- **Ignoring LLM capabilities**: Using tools without leveraging the full LLM's contextual understanding leads to less relevant results.  
  - Solution: Use the LLM's response API for richer information sharing between tools and the main query.

## Code Examples
```python
from langgraph agents re import create_react_agent
llm = LlamaCpp(
    model="gpt-5",
    max_tokens=1024,
    temperature=0.7,
    use_responses_api=True
)
llm_with_tools = llm.bind_tools(["search_travel_info", "weather_forecast"])
travel_info_agent = create_react_agent(
    model=llm,
    tools={"search_travel_info": search_travel_info, 
           "weather_forecast": weather_forecast},
    state_schema=AgentState,
    prompt="You are a helpful assistant that can search travel information and get the weather forecast. Only use the tools to find the information you need (including town names)."
)
async def main():
    print("UK Travel Assistant (type 'exit' to quit)")
    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        state = {"messages": [HumanMessage(content=user_input)]}
        response_message = travel_info_agent.invoke(state)
        print(f"Assistant: {response_message['messages'][0]['content']}")
```

## Reference Tables
| **Tool**         | **Description**                                                                 |
|-------------------|-----------------------------------------------------------------------------|
| `search_travel_info` | Searches for travel-related information about specified locations.       |
| `weather_forecast`  | Provides weather forecasts and temperature data for given towns.        |

| **Tool Execution Node Parameters** |
|-----------------------|---------------------------------------------------------------|
| `llm`                 | The LLM model used to invoke the agent.                              |
| `tools`              | List of available tools with descriptions.                                |
| `state_schema`        | Defines the structure and types for the agent's internal state.          |

## Key Takeaways
1. Combine semantic search with multiple external tools to create dynamic, context-aware agents.
2. Use prebuilt frameworks like ReAct to simplify tool orchestration and debugging.
3. Leverage LangSmith for detailed logging and analysis of agent behavior.
4. Avoid common pitfalls by using predefined tool descriptions, system messages, and LLM capabilities.

This chapter demonstrates how to build robust, flexible agents that integrate semantic search with external tools, providing dynamic recommendations based on user input and available data sources.