# Chapter 5: CHAPTER 4

## Core Idea
The chapter emphasizes how AI agents can leverage external tools (both handcrafted and provided by platforms) to extend their capabilities beyond core functionalities, enabling them to perform complex tasks through tool orchestration.

## Frameworks Introduced
- **Local Tools**: Tools that run locally within an agent's framework, such as mathematical operations or arithmetic.
  - When to use: Perform simple, predictable operations without external dependencies.
  - How: Implement basic functions and rely on built-in libraries for execution.
  
- **API-Based Tools**: Tools that interact with external services via APIs, like weather prediction or database queries.
  - When to use: When the agent needs access to external data sources or APIs.
  - How: Bind tools to APIs using wrapper classes and invoke them as methods.

- **MCP (Model Context Protocol)**: A model-agnostic interface for connecting agents with external systems.
  - When to use: For seamless integration of diverse services across platforms.
  - How: Use MCP server configurations to expose API endpoints and enable tool invocation via JSON-RPC.

- **Stateful Tools**: Tools that maintain state, such as databases or APIs requiring persistent access.
  - When to use: When tools need to interact with live data stores or perform long-running operations.
  - How: Sanitize inputs, enforce least privilege, and log interactions for observability.

## Key Concepts
- **Tool**: An execution context that represents a capability or function (e.g., mathematical operations).
- **Local Tool**: A tool that runs locally within an agent's framework.
- **API-Based Tool**: A tool that interacts with external services via APIs.
- **MCP Server**: A server that exposes API endpoints for tool invocation.

## Mental Models
Use Local Tools when you need simple, predictable operations. Use MCP-based tools when integrating diverse systems. Avoid over-reliance on custom code (Automated Tool Development) and ensure validation of outputs to prevent errors.

## Anti-patterns
- Over-reliance on custom code or poorly-maintained tools.
  - What to avoid: Inheriting complex logic from external sources without proper validation or testing.

## Code Examples
```python
from langchain_openai import ChatOpenAIModel

@tool
def multiply(x: float, y: float) -> float:
    """Multiply two numbers and return the product."""
    return x * y

@tool
def get_stock_price(ticker: str) -> float:
    """Get the current stock price for the given ticker symbol."""
    response = requests.get(f'https://api.example.com/stocks/{ticker}')
    if response.status_code == 200:
        data = response.json()
        return data["price"]
    else:
        raise ValueError(f"Failed to fetch stock price for {ticker}")

llm = ChatOpenAIModel(model_name="gpt-4o")
llm_with_tools  = llm.bind_tools([multiply, get_stock_price])

messages = [HumanMessage(content="What is the stock price of AAPL?")]
ai_msg = llm_with_tools.invoke(messages)
print(ai_msg.content)
```

This code demonstrates how to bind multiple tools (multiply and get_stock_price) to an LLM and use them in a single invocation.

## Reference Tables
| Framework        | Description                                                                 |
|-----------------|-----------------------------------------------------------------------------|
| MCP Server       | Exposes API endpoints for tool invocation using JSON-RPC over HTTPS or WebSocket. |

## Key Takeaways
1. Use local tools for simple, predictable operations.
2. Leverage external APIs when interacting with third-party services.
3. Implement validation and error handling to ensure tool reliability.
4. Use MCP-based integration for seamless cross-platform interoperability.

## Connects To
- Previous chapters on language models and foundation AI concepts.
- Future chapters on planning, orchestration, and advanced tool management strategies.