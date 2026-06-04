# Chapter 1: Prompt Chaining  

## Core Idea  
Prompt chaining is a foundational pattern for building sophisticated AI agents by breaking complex tasks into sequential steps. Each step focuses on a specific task, improving reliability and control by leveraging the model's capacity to handle simpler operations one at a time.

## Frameworks Introduced  
- **LangChain**: A framework that supports creating linear sequences of prompts and language model interactions using LCEL or LangGraph.  
  - When to use: For implementing prompt chaining workflows in Python.  
  - How: Combines multiple prompts with the language model, allowing for step-by-step processing of tasks.  

## Key Concepts  
- **Prompt Chaining**: Breaking down complex tasks into a sequence of smaller, focused steps.  
- **Context Engineering**: A methodology that enriches the information provided to an AI by including external data and system constraints.  

## Mental Models  
- Use LangChain when you need to implement prompt chaining workflows in Python.  

## Anti-patterns  
- Avoid monolithic prompts for complex tasks as they increase cognitive load and reduce reliability.  

## Code Examples  
```python
# Example code using LangChain for a two-step prompt chain

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

llm = ChatOpenAI(temperature=0)

extract_prompt = ChatPromptTemplate.from_template("Extract text: {text}")
transform_prompt = ChatPromptTemplate.from_template("Transform into JSON: {text}")

extraction_chain = extract_prompt | llm | StrOutputParser()
full_chain = {"text": extraction_chain} | transform_prompt | llm | StrOutputParser()

input_text = "The new laptop model features a 3.5 GHz octa-core processor, 16GB of RAM, and a 1TB NVMe SSD."

final_output = full_chain.invoke(input_text)
print(final_output)  
```
- **What it demonstrates**: Using LangChain to create a prompt chain that extracts technical specifications from text and transforms them into a JSON object.  

## Reference Tables  
| Framework       | Purpose                                      | When to Use               |
|-----------------|-----------------------------------------------|---------------------------|
| LangChain       | Manages chains of prompts for complex workflows | Implementing prompt chaining |
| LangGraph        | Supports stateful and cyclical computations    | Advanced agentic systems   |

## Key Takeaways  
1. Use prompt chaining when handling complex tasks that require multiple steps or reasoning phases.  
2. Frameworks like LangChain provide tools to implement these sequences effectively.  
3. Context engineering enhances the reliability of AI outputs by enriching the information provided.  

## Connects To  
- Relates to prompt engineering and language model capabilities in broader AI development contexts.