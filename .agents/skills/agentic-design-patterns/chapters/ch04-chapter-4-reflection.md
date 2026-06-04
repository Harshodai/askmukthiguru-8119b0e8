# Chapter 4: Reflection

## Core Idea
The Reflection pattern enables agents to evaluate their own output or internal state, leading to iterative refinement for improved results.

## Frameworks Introduced
- **LangChain's LCEL (Langchain Expression Language)**:
  - When to use: When you need a structured way to pass outputs between agents in LangChain.
  - How: It allows chaining agents with clear steps and context management.
  
- **Google Agent Developer Kit (ADK)**:
  - When to use: For implementing the producer-critic model in Google's ADK.
  - How: Uses sequential agents where one agent generates content, and another critiques it.

## Key Concepts
- **Evaluation Criteria**: Includes factual accuracy, coherence, style, completeness, adherence to instructions, and context preservation.
  
- **Reflection Loop**: A cycle of generate, critique, refine stages that improves output quality iteratively.

## Mental Models
- Use the producer-critic model when you need an agent to evaluate its own work or another agent's output for structured feedback. This helps in maintaining high-quality results through self-correction.

## Anti-patterns
- **No Iterative Process**: Avoid relying solely on a single pass of evaluation without iteration, as it may lead to suboptimal outputs due to the dependency on previous steps being perfect.

## Code Examples
```python
# LangChain Example with LCEL

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage
from langchain import Lcel

llm = ChatOpenAI(model="gpt-4o", temperature=0.1)

def run_reflection_loop():
    task_prompt = """..."""
    
    max_iterations = 3
    current_code = ""
    message_history = [HumanMessage(content=task_prompt)]
    
    for i in range(max_iterations):
        if i == 0:
            response = llm.invoke(message_history)
            current_code = response.content
        else:
            message_history.append(HumanMessage(content="Please refine the code..."))
            response = llm.invoke(message_history)
            current_code = response.content
        
        print(f"Generated Code (v{i+1}):")
        print(current_code)
        
        reflector_prompt = [
            SystemMessage(content="""..."""),
            HumanMessage(content=f"Original Task:\n{task_prompt}\nCode to Review:\n{current_code}"]
        ]
        critique_response = llm.invoke(reflector_prompt)
        critique = critique_response.content
        
        if "CODE_IS_PERFECT" in critique:
            print("No further critiques found. The code is satisfactory.")
            break
        else:
            print(f"Critique: {critique}")
            message_history.append(HumanMessage(content=critique))
    
    print("\nFinal Refinement:")
    print(current_code)

if __name__ == "__main__":
    run_reflection_loop()
```

## Reference Tables

| Framework | Purpose | Implementation |
|----------|---------|-----------------|
| LCEL     | Provides structured output passing in LangChain | Manages agent interactions with clear steps and context |
| ADK      | Implements multi-agent systems | Uses sequential agents for generation and critique |

## Key Takeaways
1. Use the producer-critic model to enable iterative refinement of outputs.
2. Implement reflection loops for continuous improvement, balancing thorough evaluation with efficiency.
3. Avoid single-step processes without iteration to maintain high-quality results.

## Connects To
- Chapter 1: Goal Setting - Enhances goal alignment through self-assessment.
- Chapter 2: Problem Solving - Adds a layer of solution evaluation and refinement.
- Chapter 3: Content Generation - Improves output quality through iterative critique.