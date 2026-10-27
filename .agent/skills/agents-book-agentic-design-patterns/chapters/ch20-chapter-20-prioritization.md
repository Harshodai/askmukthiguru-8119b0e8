# Chapter 20: Prioritization

## Core Idea
Prioritization is essential for AI agents operating in complex environments with limited resources. It enables agents to focus on critical tasks, enhancing efficiency and effectiveness.

## Frameworks Introduced
- **Prioritization Pattern**: 
  - When to use: In complex, dynamic environments where multiple tasks or goals exist.
  - How: Establish criteria (urgency, importance, dependencies) and evaluate tasks based on these criteria. Dynamic re-prioritization allows agents to adapt as conditions change.

## Key Concepts
- **Urgency**: Importance of task completion within a specific timeframe.
- **Importance**: Impact of the task's outcome on primary objectives.
- **Dependencies**: Tasks that must be completed before others can begin.
- **Resource Availability**: Feasibility of completing tasks given available resources.
- **Cost/Benefit Analysis**: Evaluation of task execution costs against expected benefits.
- **User Preferences**: Input from stakeholders to influence task prioritization.

## Mental Models
- Use *prioritization* when *managing complex, multi-task environments with limited resources*. Think of prioritization as a systematic approach to selecting the most critical tasks first.

## Anti-patterns
- **No Prioritization**: Failing to establish any order among tasks can lead to inefficiency and missed opportunities.
  - What to avoid: Random task assignment without considering priority criteria.

## Code Examples
```python
# Example code demonstrating prioritization in a project manager agent using LangChain

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import Tool
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor
from langchain.memory import ConversationBufferMemory

# Initialize the language model and task manager
llm = ChatOpenAI(temperature=0.5, model="gpt-4")
task_manager = SuperSimpleTaskManager()

# Define tools for the project manager agent
pm_tools = [
    Tool(
        name="create_new_task",
        func=create_new_task_tool,
        description="Create a new task with the given description.",
    ),
    Tool(
        name="assign_priority",
        func=assign_priority_to_task,
        description="Assign a priority level (P0, P1, P2) to a task.",
    ),
    Tool(
        name="assign_worker",
        func=assign_task_to_worker,
        description="Assign a task to a specific worker.",
    ),
    Tool(
        name="list_tasks",
        func=list_all_tasks,
        description="List all current tasks and their details.",
    ),
]

# Create the agent executor
pm_prompt_template = ChatPromptTemplate.from_messages([
    ("system", """You are a focused Project Manager LLM agent. Your goal is to manage project tasks efficiently.
    
    When you receive a new task request, follow these steps:
    1. First, create the task with the given description using the `create_new_task` tool.
    2. Next, analyze the user's request to see if a priority or an assignee is mentioned.
       - If a priority is mentioned (e.g., "urgent", "ASAP"), map it to P0. Use `assign_priority`.
       - If a worker is mentioned, use `assign_task_to_worker`.
    3. If any information (priority, assignee) is missing, default to P1 priority and 'Worker A'.
    4. Once the task is fully processed, use `list_tasks` to show the final state.
    
    Available workers: 'Worker A', 'Worker B', 'Review Team'
    Priority levels: P0 (highest), P1 (medium), P2 (lowest)"""),
    ("placeholder", "{chat_history}"),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}")
])

pm_agent = create_react_agent(llm, pm_tools, pm_prompt_template)
pm_agent_executor = AgentExecutor(
    agent=pm_agent,
    tools=pm_tools,
    verbose=True,
    handle_parsing_errors=True,
    memory=ConversationBufferMemory(memory_key="chat_history", return_messages=True),
)

# Example interaction
print("Handling urgent login system implementation request.")
response = pm_agent_executor.ainvoke({"input": "Create a task to implement a new login system. It's urgent and should be assigned to Worker B."})
```

- **What it demonstrates**: The code implements a project manager agent using prioritization, demonstrating how to create tasks, assign priorities, and list all tasks.

## Reference Tables
| Criteria                | Description                                      |
|------------------------|--------------------------------------------------|
| Urgency               | Importance of task completion within timeframe  |
| Importance             | Impact on primary objectives                   |
| Dependencies           | Tasks that must be completed before others      |
| Resource Availability   | Feasibility of completing tasks                 |
| Cost/Benefit Analysis   | Task execution costs vs expected benefits       |
| User Preferences        | Input from stakeholders                           |

## Key Takeaways
1. Prioritization is essential for agents to focus on critical tasks in complex environments.
2. Establishing clear criteria (urgency, importance, dependencies) and evaluating tasks based on these criteria ensures focused action.
3. Dynamic re-prioritization allows agents to adapt to changing conditions.

## Connects To
- Agent Behavior
- Decision-Making Processes
- Resource Management