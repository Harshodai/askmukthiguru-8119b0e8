# Chapter 2: Designing Agent Systems

## Core Idea  
The chapter emphasizes designing an agent system by focusing on a specific, bounded workflow to automate customer support tasks. It demonstrates how to use LangChain tools and LLMs effectively for narrow but impactful automation.

## Frameworks Introduced  
- **LangChain**: A framework for building custom LLM integrations, used to create the `cancel_order` tool and agent brain.  
  - When to use: For automating specific tasks with LLMs.  
  - How: Define tools with parameters, integrate them into an agent brain that uses LLM prompts to decide actions.

## Key Concepts  
- **Single Business Tool**: A focused function (e.g., `cancel_order`) that performs a narrow task.  
- **Agent Brain**: An LLM model that decides which tool to call and processes its output.  
- **StateGraph**: A Directed Acyclic Graph for coordinating agent interactions, ensuring predictable workflows.

## Mental Models  
- Use LangChain when you need to automate specific tasks with LLMs. Think of it as a structured framework for creating custom LLM integrations.

## Anti-patterns  
- Avoid broad goals that lead to edge cases or vague success metrics. Instead, focus on clear, measurable outcomes for narrow tasks.

## Code Examples  
```python
# Example of constructing the agent system
from langchain.tools import tool
from langchain_openai.chat_models import ChatOpenAI

@tool
def cancel_order(order_id: str) -> str:
    """Cancel an order that hasn't shipped."""
    return f"Order {order_id} has been cancelled."

def call_model(state):
    # System prompt instructs the LLM to interact with tools and generate responses.
    # Uses state messages, order info, and tool calls to decide actions.

def construct_graph():
    g = StateGraph({"order": None, "messages": []})
    g.add_node("assistant", call_model)
    return g.compile()

graph = construct_graph()
# Invoke the agent with example input
result = graph.invoke({"order": {"order_id": "B73973"}, "messages": [HumanMessage(content='...')]}
```

This code demonstrates creating a narrow workflow for order cancellation, ensuring predictable and testable behavior.

## Reference Tables  
| **Metric**         | **Evaluation Aspect**                                                                 |
|--------------------|---------------------------------------------------------------------------------------|
| Tool Accuracy      | Ensures the correct `cancel_order` tool is called.                                 |
| Parameter Precision | Verifies exact match of `order_id` in tool calls.                                   |
| Confirmation Clarity| Checks for clear, correct messages to customers.                                     |

## Key Takeaways  
1. Start with a clear, bounded workflow for automation.  
2. Use LangChain tools to create focused functions (e.g., `cancel_order`).  
3. Test agent functionality with evaluation metrics like tool calls and message clarity.  
4. Avoid broad or vague goals; focus on specific tasks for effective automation.

## Connects To  
- Relates to Chapter 1's introduction to agent design principles.  
- Builds upon later chapters on evaluation methods and StateGraph usage.