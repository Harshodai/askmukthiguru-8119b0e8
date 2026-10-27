# Chapter 5: Tool Use (Function Calling)

## Core Idea
The most important concept taught in this chapter is the integration of external tools into an agent's workflow using function calling. This allows agents to interact with external systems, access real-time data, and perform actions beyond their intrinsic capabilities.

## Frameworks Introduced
- **LangChain**: A framework that simplifies tool definition using decorators like `@tool` and provides utilities for creating tool-calling agents (e.g., `create_tool_calling_agent`).
  - When to use: When building agents that need to interact with external systems or retrieve dynamic information.
  - How: Defines tools as Python objects with descriptions, parameters, and outcomes; integrates them into agents using `@tool` decorators.

- **Google Agent Developer Kit (ADK)**: A library for creating custom agents, including predefined tools like Google Search, Code Interpreter, and Vertex AI Search.
  - When to use: For developers building enterprise-grade agents that interact with external APIs, databases, or search engines.
  - How: Provides a structured API for defining tools (e.g., `google_search`), integrating them into agents using runners and sessions.

- **CrewAI**: An agent framework focused on complex workflows involving multiple systems.
  - When to use: For building sophisticated agentic systems that need to interact with external digital environments.
  - How: Utilizes InMemorySessionService for session management, Runner for executing agents, and tools like `google_search` or custom code executors.

## Key Concepts
- **Tool Use Pattern**: Describes how an LLM can use external functions or tools by generating structured function calls. This enables the agent to retrieve information from external sources or execute actions.
  - Example: An agent using Google Search to fetch current weather data and incorporating it into its response.

- **Function Calling**: A method where an LLM generates a request (function call) to an external tool, which is then executed by an orchestrator. The result is fed back to the LLM for further processing.
  - Example: An agent using a Code Interpreter tool to execute Python code and return its output.

- **Agentic Frameworks**: Tools that allow agents to delegate tasks to external systems while maintaining control over the interaction flow (e.g., Google ADK, LangChain).
  - Example: Using Vertex AI Search to retrieve documents based on user queries.

## Mental Models
- Use **LangChain** when you need a flexible and extensible way to integrate tools into your agents.
  - Think of LangChain as a "one-stop shop" for defining and executing tool calls within an agent's workflow.

- Use **Google ADK** when you require enterprise-grade control over external systems, such as accessing proprietary databases or performing complex calculations.
  - Think of Google ADK as a powerful toolkit for building agents that interact with specific external services.

## Anti-Patterns
- **Avoid Intrinsic Knowledge**: Do not use external tools when the information can be retrieved directly from the agent's training data. For example, checking current weather using an external tool instead of relying on the agent's internal knowledge.

## Code Examples
```python
# LangChain Example: Google Giveaway Tool Integration
from langchain_google_openai import ChatGoogleGenerativeAI 
from langchain.tools import tool as tools

google_api_key = getpass.getpass("Enter your Google API key: ")
google_api_key = google_api_key.encode()

@langchain_tool(name="Google Giveaway Tool") 
def search_information(query: str) -> str:
    """Provides helpful information on a given topic."""
    print(f"Query: {query}")
    return f"The current information about {query} is as follows."

tools.addTool(search_information)

agents = create_tool_calling_agent(llm, tools=tools)
```

```python
# CrewAI Example: Custom Tool Integration
import os, getpass 
import asyncio 
from typing import List 
from datetime import date 

# Setup variables required for Session setup and Agent execution 
APP_NAME="basic_search_agent" 
USER_ID="user1234" 
SESSION_ID="1234"

# Define Agent with access to search tool 
code_agent = LLMAgent( 
  name="basic_search_agent", 
  model="gemini-2.0-flash", 
  description="Agent to answer questions by searching the internet.", 
  model_parameters={"temperature": 0.0} 
)

# Agent Interaction 
async def call_agent_async(query: str): 
    """Helper function to call the agent with a query."""
    print(f"\n--- Running Query: {query} ---") 
    final_response_text = "No final text response created." 
    try: 
        # Use run_async to send the query to the agent and process the result 
        async for event in runner.run_async(user_id=USER_ID, session_id=SESSION_ID, new_message=content): 
            print(f"Event ID: {event.id}, Author: {event.author}") 
 
            if hasattr(event, 'content_part_delta') and event.content_part_delta: 
                print(event.content_part_delta.text, end="", flush=True) 
 
            # Process the final response and its associated metadata 
            if event.is_final_response(): 
                print() # Newline after the streaming response 
                if event.grounding_metadata: 
                    print(f"  (Source Attributions: {len(event.grounding_metadata.grounding_attributions)} sources found)") 
                else: 
                    print("  (No grounding metadata found)") 
                print("-" * 30) 
 
    except Exception as e: 
        print(f"\nAn error occurred: {e}") 

# Main async function to run the examples 
async def run_vsearch_example(): 
   # Replace with a question relevant to YOUR datastore content 
   await call_vsearch_agent_async("Summarize the main points about 
the Q2 strategy document.") 
   await call_vsearch_agent_async("What safety procedures are 
mentioned for lab X?") 
 
# Main execution block 
if __name__ == "__main__": 
   if not DATASTORE_ID: 
       print("Error: DATASTORE_ID environment variable is not set.") 
   else: 
       try: 
           asyncio.run(run_vsearch_example()) 
       except RuntimeError as e: 
           # This handles cases where asyncio.run is called in an 
           # running event loop (like a Jupyter notebook). 
           if "cannot be called from a running event loop" in str(e): 
               print("Skipping execution in a running event loop. Please run this script directly.") 
           else: 
               raise e 
```

## Reference Tables
| Framework       | Key Features                                                                 |
|-----------------|-----------------------------------------------------------------------------|
| LangChain       | Simplifies tool definition with decorators and provides utilities for tool-calling agents. |
| Google ADK      | Offers predefined tools like Google Search, Code Interpreter, and Vertex AI Search. |
| CrewAI          | Specializes in complex workflows involving multiple external systems. |

## Key Takeaways
1. Use LangChain when you need a flexible and extensible way to integrate tools into your agents.
2. Leverage Google ADK for enterprise-grade control over external systems like APIs, databases, or search engines.
3. Use CrewAI for building sophisticated agentic systems that interact with multiple external digital environments.

## Connects To
- Function Calling in LangChain
- Extending Agents to Interact with External Services