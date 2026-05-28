# Chapter 35: Multi-Agent Systems

## Core Idea
Multi-agent systems enable the creation of robust AI applications by combining multiple specialized agents to handle complex tasks that single-agent systems cannot address.

## Frameworks Introduced
- **Tool-Based Agents**: Tools are reusable components with specific functions, designed for tool-based workflows.
  - When to use: When you need modular, reusable functionality across different parts of your application.
  - How: Define tools with a name, description, and implementation (e.g., SQLDatabaseToolkit).

- **ReAct Agents**: Built-in agents that combine multi-tool execution, error handling, and LLM-based routing.
  - When to use: For creating sophisticated, reusable AI agents that can handle complex workflows.
  - How: Use predefined schemas for tools and create agents with specific prompts.

## Key Concepts
- **Tool**: A reusable component with a name, description, and implementation (e.g., ` hotel_db_toolkit`).
- **Agent**: An AI tool that uses tools to perform actions or provide information. Agents can be specialized (e.g., travel_info_agent) or general-purpose.
- **Supervisor Agent**: Manages multiple agents, coordinating their execution for complex requests.

## Mental Models
Use multi-agent systems when you need flexibility and collaboration between agents. Think of agents as dynamic tools that adapt to the problem at hand.

## Anti-patterns
- Avoid monolithic architectures, which are brittle and fail to scale or adapt to changing requirements.
  - What to avoid: Using a single agent or tool stack for complex tasks without proper orchestration.

## Code Examples
```python
# Example of creating a simple multi-agent system with LangGraph
from langgraph import AgentState
from langgraph.supervisor import create_supervisor

# Define tools
class HotelDBToolkit:
    def __init__(self):
        self._db = SQLDatabase.from_uri("sqlite:///hotel_db.db")

    @property
    def db(self):
        return self._db

    def get_hotels(self, name: str, check_in: str) -> List[Dict]:
        return self.db.search_hotels(name=name, check_in=check_in)

# Define agents
travel_info_agent = create_react_agent(
    model="gpt-4",
    tools=[HotelDBToolkit],
    state_schema=AgentState,
    prompt="""You are a travel information assistant that can search hotel databases and provide relevant information about destinations in Cornwall.
            Only use the tools to find the information you need (including town names).""",
)

accommodation_booking_agent = create_react_agent(
    model="gpt-4",
    tools=[check_bnb_availability],
    state_schema=AgentState,
    prompt="""You are an accommodation booking agent that can check BnB availability and price for hotels in Cornwall. You can use the tools to get information about destinations.
            If the user does not specify the accommodation type, you should check both hotels and BnBs.""",
)

# Create a supervisor
travel_assistant = create_supervisor(
    agents=[travel_info_agent, accommodation_booking_agent],
    model="gpt-5",
    supervisor_name="Travel Assistant",
    prompt=("""
        You are a travel assistant that manages two specialized agents: a travel information agent and an accommodation booking agent.
        You can answer user questions that might require calling both agents when needed.
        Decide which agent(s) to use for each user request and coordinate their responses.
    """)
).compile()
```

## Reference Tables
```markdown
| **Tool**       | **Description**                                                                 |
|-----------------|-----------------------------------------------------------------------------|
| SQLDatabaseToolkit | Retrieves hotel information from a SQLite database.                               |
| check_bnb_availability | Simulates BnB availability for Cornwall properties.                              |
```

## Key Takeaways
1. Use multi-agent systems to create flexible, dynamic AI applications that handle complex tasks.
2. Leverage tools and supervisors to orchestrate agent collaboration on multipart queries.
3. Always design agents with clear purposes and use cases to ensure they complement each other.

## Connects To
- Frameworks: Tool-Based Agents, ReAct Agents
- Chapters: Building an Accomp dining Assistant, Router-Based Multi-Agent Travel Assistant