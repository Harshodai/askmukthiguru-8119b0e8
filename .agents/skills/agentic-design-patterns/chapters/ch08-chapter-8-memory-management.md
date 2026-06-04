# Chapter 8: Memory Management

## Core Idea
Agents must manage both short-term context within a conversation and long-term knowledge across sessions to perform complex tasks, personalize interactions, and learn from experiences.

## Frameworks Introduced
- **Google's Adaptive Data Kit (ADK)**:
  - When to use: For building intelligent agents that need structured memory management.
  - How: ADK provides `Session` for managing conversation history, `State` for temporary data, and `MemoryService` for long-term knowledge storage.

## Key Concepts
- **Short-Term Memory (STM)**: Temporary context within a single chat thread, managed by the agent's state. Limited to the current interaction window.
- **Long-Term Memory (LTM)**: Persistent information stored externally, accessible through memory services like Vertex AI's MemoryBank or LangGraph.

## Mental Models
- Use **existing knowledge** when building new systems to avoid reinventing solutions and ensure alignment with established practices.

## Anti-patterns
- Avoid adding state directly to the session dictionary without proper mechanisms for context persistence. This can lead to inconsistent data handling across interactions.

## Code Examples
```python
# Example of using Vertex AI MemoryBank in Google ADK
from googleadsdk memory import VertexAiMemoryBankService

agent_engine_id = "your-engine-id"
memory_service = VertexAiMemoryBankService(project="PROJECT_ID", location="LOCATION", agent_engine_id=agent_engine_id)

session = await session_service.get_session(app_name="your-app-name", user_id="your-user-id", session_id="your-session-id")
await memory_service.add_session_to_memory(session)
```

```python
# Example of using LangChain's ConversationBufferMemory
from langchain.memory import ConversationBufferMemory

llm = ChatOpenAI()
memory = ConversationBufferMemory(memory_key="chat_history")

# Add user and system messages to the conversation buffer
memory.save_context({"input": "I'm Jane"}, {"output": "Hello, Jane!"})
```

## Reference Tables
| Parameter | Description |
|---|---|
| Vector Dimension | Determines similarity accuracy in semantic search. Higher dimensions improve recall but increase computational cost. |

## Key Takeaways
1. Use **existing knowledge** to build systems that adapt and learn from interactions.
2. Implement short-term memory for immediate context within conversations using tools like Google ADK's Session and State.
3. Leverage long-term memory services (e.g., Vertex AI MemoryBank or LangGraph) for persistent, searchable information across sessions.
4. Avoid direct state modifications to session dictionaries without proper event handling mechanisms.

## Connects To
- Chapter 7: Agent Development Workflow  
- Chapter 9: Practical Applications & Case Studies