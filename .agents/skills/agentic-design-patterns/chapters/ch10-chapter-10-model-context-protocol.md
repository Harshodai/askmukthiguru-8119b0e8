# Chapter 10: Model Context Protocol

## Core Idea
The Model Context Protocol (MCP) is an open standard that enables large language models (LLMs) and intelligent agents to interact with external systems, including databases, APIs, and tools, by providing a standardized communication framework.

## Frameworks Introduced
- **Model Context Protocol (MCP)**: An open standard for LLM-external system interaction.  
  - When to use: When building complex AI/AGI systems that require dynamic access to external capabilities.  
  - How: Through client-server architecture, exposing resources, tools, and prompts in a standardized manner.

## Key Concepts
- **Model Context Protocol (MCP)**: A universal interface for LLMs to communicate with external systems.
- **Client**: An application or agent that interacts with MCP servers using predefined requests and responses.
- **Server**: A component that exposes tools, resources, and prompts to MCP clients according to the protocol.
- **Resource**: Static data (e.g., files in a database) that can be retrieved by agents.
- **Tool**: An executable function provided by MCP servers for specific actions.

## Mental Models
- Use MCP when building complex systems requiring dynamic external interactions.  
  - Think of MCP as enabling scalable, interoperable AI/AGI capabilities through standardized communication.

## Anti-patterns
- **Avoid ad-hoc integration without MCP**: Integrating external tools manually can lead to non-reusable and complex setups.

## Code Examples
```python
# fastmcp_server.py (example code)
# This script demonstrates how to create a simple MCP server using FastMCP.
from fastmcp import FastMCP, Client

# Initialize the FastMCP server.
mcp_server = FastMCP()

# Define a simple tool function that generates a greeting.
@mcp_server.tool
def greet(name: str) -> str:
    """Generates a personalized greeting."""
    return f"Hello, {name}! Nice to meet you."

# Start the server on port 8000 (localhost).
if __name__ == "__main__":
    mcp_server.run(transport="http", host="127.0.0.1", port=8000)
```

- **What it demonstrates**: A simple Python script that sets up an MCP server exposed to agents, showcasing how tools can be registered and used.

## Reference Tables
| Component      | Function in MCP          |
|----------------|-------------------------|
| Client         | Connects to MCP servers   |
| Server         | Exposes resources/tools  |
| Resource       | Static data sources      |
| Tool           | Executable functions     |
| Prompt         | Guides client actions    |

## Key Takeaways
1. MCP is essential for building scalable, interconnected AI systems by standardizing external interactions.
2. Using MCP enables agents to access diverse external tools and data sources efficiently.
3. MCP provides a foundation for interoperability between LLMs and external systems.

## Connects To
- Architecture of LLMs (Chapter 9)
- Integration of AI capabilities with external services