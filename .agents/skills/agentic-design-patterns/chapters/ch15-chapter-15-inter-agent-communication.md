# Chapter 15: Inter-Agent Communication

## Core Idea
The Google A2A protocol enables collaboration between AI agents built on different frameworks by providing an open, standardized communication method.

## Frameworks Introduced
- **Google Agent Development Kit (ADK)**:
  - When to use: Building agents for complex tasks requiring specialized skills.
  - How: Integrates with tools like Google Calendar via `CalendarToolset`.
  
- **LangGraph**:
  - When to use: Implementing custom language understanding agents.
  - How: Defined through JSON-RPC 2.0 methods and payloads.

- **CrewAI**:
  - When to use: Developing agents for structured data processing tasks.
  - How: Configured with input/output modes, capabilities, and discovery parameters.

## Key Concepts
- **Agent Card**: A digital identity defining an agent's capabilities, skills, and network address.  
- **Interaction Mechanisms**: Includes synchronous requests, asynchronous polling, streaming updates (Server-Sent Events), and push notifications.
- **Security**: Built-in mechanisms like mutual TLS (mTLS) and authentication requirements ensure secure communication.

## Mental Models
Use A2A when building multi-agent systems to enable collaboration between agents built on different frameworks. Think of A2A as the glue that connects islands of AI, allowing them to work together seamlessly.

## Anti-patterns
Avoid not integrating agents properly by failing to discover or delegate tasks. This can lead to redundant code and inefficiency in workflows.

## Code Examples
```python
from google.adk.agents import LlmAgent
from google.adk.tools.google_api_tool import CalendarToolset

async def create_agent(client_id, client_secret):
    toolset = CalendarToolset(client_id=client_id, client_secret=client_secret)
    return LlmAgent(
        model='gemini-2.0-flash-001',
        name='Calendar Agent',
        description="Manages a user's calendar",
        tools=await toolset.get_tools(),
    )
```
This demonstrates creating an ADK agent configured for Google Calendar integration.

## Reference Tables
| Framework | Key Components and Use Cases |
|----------|------------------------------|
| ADK      | Tools like `CalendarToolset` for integrating external APIs. |
| LangGraph | Custom language understanding agents via JSON-RPC 2.0. |
| CrewAI   | Agents for structured data processing tasks. |

## Key Takeaways
1. Use A2A to enable collaboration between AI agents built on different frameworks.
2. Ensure secure communication using mechanisms like mTLS and authentication.
3. Leverage modular architecture by delegating tasks among specialized agents.

## Connects To
- Agent Discovery Patterns  
- Model Context Protocol (MCP)