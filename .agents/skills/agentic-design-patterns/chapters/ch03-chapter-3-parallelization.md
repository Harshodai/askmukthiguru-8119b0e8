# Chapter 3: Parallelization

## Core Idea
Parallelization is essential for optimizing agent workflows by enabling concurrent execution of independent tasks, significantly reducing processing time in complex systems.

## Frameworks Introduced
- **LangChain Expression Language (LCEL)**:
  - When to use: When designing agent flows that involve multiple independent operations.
  - How: Utilizes `Runnable` constructs like `| (for sequential)`, `| (for parallel execution)` and `| by` for managing concurrency.

## Key Concepts
- **Independent Tasks**: Tasks that do not depend on each other's output, allowing parallel execution without waiting.
- **Sequential vs. Parallel Execution**: Sequential tasks wait for predecessors, while parallel tasks run concurrently to save time.
- **Latency Reduction**: Concurrent task execution reduces overall workflow time by eliminating sequential dependencies.

## Mental Models
- Use LangChain's LCEL when your agent needs to execute multiple independent operations in parallel. Think of LCEL as a tool that enables defining and managing concurrent workflows within the LangChain framework.

## Anti-patterns
- **Sequential Execution**: Avoid this when tasks can be executed independently, as it leads to unnecessary delays and increased latency.

## Code Examples
```python
# Example using LangChain's RunnableParallel in Python

from typing import Optional 
from langchain_openai import ChatOpenAI 
from langchain_core.prompts import ChatPromptTemplate 
from langchain_core.output_parsers import StrOutputParser 
from langchain_chain import LangChain 

# Define independent chains
summarize_chain = (ChatPromptTemplate.from_messages([("system", "Summarize the following topic concisely:"), ("user", "{topic}")]) | llm | StrOutputParser())
questions_chain = (ChatPromptTemplate.from_messages([("system", "Generate three interesting questions about the following topic:"), ("user", "{topic}")]) | llm | StrOutputParser())
terms_chain = (ChatPromptTemplate.from_messages([("system", "Identify 5-10 key terms from the following topic, separated by commas:"), ("user", "{topic}")]) | llm | StrOutputParser())

# Build parallel workflow
map_chain = RunnableParallel(
    { 
        "summary": summarize_chain, 
        "questions": questions_chain, 
        "key_terms": terms_chain, 
        "topic": RunnablePassthrough(),  
    } 
)

full_parallel_chain = map_chain | synthesis_prompt | llm | StrOutputParser()

async def run_parallel_example(topic: str) -> None:
    try:
        response = await full_parallel_chain.ainvoke(topic)
        print("Final Response:", response)
    except Exception as e:
        print(f"Error occurred during chain execution: {e}")

# Example using Google ADK's ParallelAgent
from google.adk.agents import LlmAgent, ParallelAgent

researcher_agent_1 = LlmAgent(
    name="RenewableEnergyResearcher",
    model=GEMINI_MODEL,
    instruction="""You are an AI Research Assistant specializing in energy. 
    Research the latest advancements in 'renewable energy sources'. 
    Use the Google Search tool provided. 
    Summarize your key findings concisely (1-2 sentences). 
    Output *only* the summary.""",
    output_key="renewable_energy_result"
)

researcher_agent_2 = LlmAgent(
    name="EVResearcher",
    model=GEMINI_MODEL,
    instruction="""You are an AI Research Assistant specializing in transportation. 
    Research the latest developments in 'electric vehicle technology'. 
    Use the Google Search tool provided. 
    Summarize your key findings concisely (1-2 sentences). 
    Output *only* the summary.""",
    output_key="ev_technology_result"
)

researcher_agent_3 = LlmAgent(
    name="CarbonCaptureResearcher", 
    model=GEMINI_MODEL,
    instruction="""You are an AI Research Assistant specializing in climate solutions. 
    Research the current state of 'carbon capture methods'. 
    Use the Google Search tool provided. 
    Summarize your key findings concisely (1-2 sentences). 
    Output *only* the summary.""",
    output_key="carbon_capture_result"
)

parallel_research_agent = ParallelAgent(
    sub_agents=[researcher_agent_1, researcher_agent_2, researcher_agent_3],
    description="Runs multiple research agents in parallel to gather information."
)

merger_agent = LlmAgent(
    name="SynthesisAgent",
    model=GEMINI_MODEL,
    instruction="""You are an AI Assistant responsible for combining research findings into a structured report. 
    Your primary task is to synthesize the following research summaries, clearly attributing findings to their source areas. 
    Structure your response using headings for each topic. Ensure the report is coherent and integrates the key points smoothly.""",
    description="Combines research findings from parallel agents into a structured, cited report."
)

sequential_pipeline_agent = SequentialAgent(
    sub_agents=[parallel_research_agent, merger_agent],
    description="Coordinates parallel research and synthesizes the results."
)

root_agent = sequential_pipeline_agent
```

## Reference Tables

| Framework | Key Mechanism | Use Case Example |
|----------|---------------|------------------|
| LangChain (LCEL) | `Runnable` constructs for parallel execution | Concurrent summarization, question generation, and content synthesis. |
| Google ADK | ParallelAgent for concurrent task execution and MergerAgent for result synthesis | Parallel research agent followed by a synthesizer agent |

## Key Takeaways
1. Use parallelization to execute independent tasks concurrently.
2. Choose frameworks like LangChain's LCEL or Google ADK based on your specific needs.
3. Structure code with runnables for concurrent execution and ensure tasks are truly independent.
4. Avoid sequential execution when tasks can be processed in parallel.

## Connects To
- Agent Design Fundamentals
- Framework Selection Guide