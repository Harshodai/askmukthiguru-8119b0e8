```markdown
# Chapter 2: Routing

## Core Idea
The Routing pattern enables agentic systems to dynamically select appropriate actions or tools based on input context, transforming static workflows into flexible, adaptive processes.

## Frameworks Introduced
- **LangChain**: A framework that supports routing using LLM-based methods and model-based classification.
  - When to use: Ideal for integrating routing logic with existing language models or custom classifiers.
  - How: Defines routing logic through prompts, embeddings, rules, or machine learning models.

- **Google ADK**: A structured environment for defining agents and their capabilities, supporting Auto-Flow for dynamic delegation.
  - When to use: Suitable for systems requiring explicit sub-agent delegation based on predefined instructions.
  - How: Agents are defined with tools (functions) and sub-agents, with routing handled automatically by the framework.

## Key Concepts
- **LLM-based Routing**: Utilizes large language models to analyze input and output a specific identifier or instruction that directs task selection or distribution. 
- **Embedding-based Routing**: Employs vector embeddings of inputs to find similar patterns in an operational database for semantic routing.
- **Rule-based Routing**: Uses predefined rules (e.g., if-else statements) based on keywords or structured data extracted from input.
- **Machine Learning Model-Based Routing**: Employs discriminative models trained on a corpus of labeled data to perform supervised classification.

## Mental Models
- Use **LLM-based routing** when you need flexible, context-aware decision-making that leverages large language models. Think of LLMs as dynamic selectors for routing based on input analysis.
- Use **Embedding-based routing** when you require semantic understanding and similarity matching between input queries and predefined patterns or categories.

## Anti-patterns
- **Static Sequential Processing**: When a system follows a fixed, predetermined workflow without adapting to context or changing conditions. This limits adaptability and fails to leverage conditional logic for dynamic decision-making.

## Code Examples
```python
# Example from LangChain: Routing in action
from langchain_google_genai import ChatGoogleGenerAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableBranch

llm = ChatGoogleGenerAI(model="gemini-2.5-flash", temperature=0)

branches = {
    "booker": RunnablePassthrough.assign(output=lambda x: f"Booking action for '{x['request']['request']}' has been simulated."),
    "info": RunnablePassthrough.assign(output=lambda x: f"Info handler processed request: '{x['request']['request']}'"),
    "unclear": RunnablePassthrough.assign(output=lambda x: f"Coordinator could not delegate request: '{x['request']['request']}' or any other unclear input. Please clarify.")
}

# Define the router chain and delegation branch
coordinator_router_prompt = ChatPromptTemplate.from_messages([
    ("system", """Analyze the user's request and determine which specialist handler should process it. 
                - If the request is related to booking flights or hotels, output 'booker'. 
                - For all other general information questions, output 'info'. 
                - If the request is unclear or doesn't fit either category, output 'unclear'."""),
    ("user", "{request}")
])

if llm:
    coordinator_router_chain = coordinator_router_prompt | llm | StrOutputParser()
else:
    coordinator_router_chain = coordinator_router_prompt | StrOutputParser()

delegation_branch = RunnableBranch(
    (lambda x: x['decision'].strip().lower() == 'booker', branches["booker"]),
    (lambda x: x['decision'].strip().lower() == 'info', branches["info"]),
    branches["unclear"]
)

coordinator_agent = {
    "decision": coordinator_router_chain,
    "request": RunnablePassthrough()
} | delegation_branch | (lambda x: x['output'])
```

This code demonstrates how routing can be integrated into a real application using LangChain and Google's Generative AI. It shows the use of prompts, LLMs, and branching logic to route requests to appropriate handlers.

## Reference Tables
| Framework | Key Feature                                                                 |
|----------|-----------------------------------------------------------------------------|
| LangChain | Supports LLM-based, embedding-based, rule-based, and ML-based routing through customizable prompt templates and output parsers. |
| Google ADK | Implements Auto-Flow for dynamic delegation by defining agents with explicit sub-agents and tools. |

## Key Takeaways
1. Use **LLM-based routing** when you need flexible, context-aware decision-making that leverages large language models.
2. Use **Embedding-based routing** when you require semantic understanding and similarity matching between input queries and predefined patterns or categories.
3. Implement **rule-based routing** for systems requiring explicit conditional logic based on keywords or structured data.
4. Employ **machine learning model-based routing** for tasks that involve supervised classification of input patterns.

## Connects To
- Relates to process mining, workflow optimization, and dynamic application composition in operational intelligence systems.
```