# Chapter 6: Planning

## Core Idea
The chapter emphasizes the importance of Goal-Oriented Planning as a foundational strategy for intelligent agents to achieve complex objectives by breaking them into actionable steps.

## Frameworks Introduced
- **Goal-Oriented Planning**: A structured approach where an agent creates a sequence of actions (a plan) to move from an initial state towards a goal.  
  - When to use: Complex tasks that require foresight and adaptability.  
  - How: Identify the initial state, define the goal, and create actionable steps or subtasks.

## Key Concepts
- **Planning Pattern**: A methodology for agents to formulate sequences of actions to achieve complex goals.
- **Goals-Subtasks-Materials (GSM) Structure**: Breaking down tasks into specific, manageable subtasks with defined outputs.
- **Adaptability**: The ability to modify plans in real-time based on new information or changing constraints.

## Mental Models
- Use Goal-Oriented Planning when you need to achieve a complex goal that can't be reached by a single action. Think of it as systematically breaking down the problem into smaller, manageable parts.
- Avoid rigid task execution without planning (e.g., following predefined workflows) because they fail to adapt to new information or constraints.

## Anti-patterns
- **Rigid Task Execution**: Performing tasks without considering their dynamic nature or incorporating feedback loops.  
  - What to avoid: Using simple task-execution agents that don't allow for replanning based on new information.

## Code Examples
```python
# Example of Goal-Oriented Planning in CrewAI

high_level_task = Task(
    description=(f"1. Create a bullet-point plan for a summary on the topic: '{topic}'.\n" 
                f"2. Write the summary based on your plan, keeping it around 200 words."),
    expected_output=(  
        "A final report containing two distinct sections:\n\n"
        "### Plan\n" 
        "- A bulleted list outlining the main points of the summary.\n\n" 
        "### Summary\n" 
        "- A concise and well-structured summary of the topic."
   ), 
    agent=planner_writer_agent, 
)
```

This code demonstrates Goal-Oriented Planning by defining a task with clear descriptions for both the plan and expected output.

## Reference Tables
<No reference tables provided in the content>

## Key Takeaways
1. Use Goal-Oriented Planning when dealing with complex goals that require foresight and adaptability.
2. Break down tasks into actionable subtasks using the GSM structure to ensure clarity and manageability.
3. Incorporate adaptability into plans to handle unexpected challenges or new information.

## Connects To
- Relates to task automation, workflow management, and dynamic systems design.