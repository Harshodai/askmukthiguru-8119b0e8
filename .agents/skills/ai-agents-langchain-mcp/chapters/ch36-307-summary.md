# Chapter 13: Building and Consuming MCP Servers Summary

## Core Idea
MCP (Model Context Protocol) enables external data sources to be exposed as tools within agents, allowing for seamless integration with third-party services like weather forecasting, APIs, and more. This chapter demonstrates how to build, test, and integrate MCP servers into agent applications.

## Frameworks Introduced
- **MCP**: A protocol for exposing external data sources as tools in AI applications.
  - When to use: Integrating external data sources or APIs into agents.
  - How: Exposing features through MCP tools that can be called like native functionalities.
  
### Key Concepts
- **MCP Server**: A service that exposes one or more MCP tools for agent access.
- **FastMCP 2**: An open-source implementation of the MCP protocol, supporting both local and remote server setups.

## Mental Models
- Use MCP when you need to integrate external data sources into an AI application. It allows modular and scalable integration by exposing features as tools.

## Anti-patterns
- Avoid monolithic architectures that isolate external services from your application's logic.
  - MCP provides a flexible, modular approach for integrating third-party tools.

## Code Examples
```python
from fastmcp import FastMCP
import os

ACCUWEATHER_API_KEY = "YOUR_API_KEY"
base_url = "http://data.blotter.com/surface/queries/v1/search"

class AccuWeatherMCPServer:
    def __init__(self):
        self.url = f"{base_url}/locations/v1/search?api_key={ACCUWEATHER_API_KEY}"
    
    async def get_weather_conditions(self, location: str) -> Dict:
        params = {"key": os.getenv("ACCUWEATHER_API_KEY")}
        async with Client("http://localhost:8020") as session:
            client = session_tools
```

This example demonstrates setting up and testing an MCP server using FastMCP 2.

## Reference Tables
| Parameter                  | Value/Implementation |
|----------------------------|-----------------------|
| MCP Server URL              | `http://127.0.0.1:8020/accu-mcp-server` |
| HTTP Method for Search      | `streamable-http`        |

## Key Takeaways
1. Use MCP to integrate external data sources into your agents, enabling real-world applications.
2. Test MCP servers with tools like MCP Inspector to ensure compatibility and functionality.
3. Follow best practices for security and error handling when deploying MCP-based solutions.

## Connects To
- Chapter 12: Understanding the Purpose and Architecture of MCP Servers
- Chapter 14: Advanced Integration and Collaboration with MCP Servers