# Chapter 21: 4. Chain Prompting

## Core Idea  
Chain Prompting enables sequential prompting where each prompt's output informs the next, allowing for iterative refinement and information extraction.

## Frameworks Introduced  
- **PromptTemplate Class**: A LangChain feature designed to create dynamic prompts with flexible inputs, ideal for constructing chain prompting sequences that rely on previous responses.  

### When to Use:  
When you need to link multiple prompts where each subsequent prompt builds upon the prior response to achieve a specific outcome.

### How:  
1. Create templates for each prompt, incorporating placeholders for variables like {scientist} or {fact}.  
2. Initialize an LLM using LangChain's LLMChain class with these templates.  
3. Run the first prompt and extract relevant information (e.g., the name of a scientist).  
4. Use this extracted data as input for the next prompt in the chain, iterating as needed to reach the desired result.

## Key Concepts  
- **Template Placeholder**: A reserved word or variable within a prompt template that allows dynamic input during execution.  

## Mental Models  
Use PromptTemplate when you want to create adaptive and iterative prompting systems. Think of it as a tool for building self-referential, context-aware prompts.

## Anti-patterns  
Avoid reusing the same prompt without updating it based on previous responses. This can lead to repetitive or irrelevant outputs if not carefully managed.

## Code Examples  
```python
# Example 1: Initializing LLM and creating prompts
llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0)
template_question = """What is the name of the famous scientist who developed the theory of general relativity? Answer:"""
prompt_question = PromptTemplate(template(template_question), input_variables=[])

# Example 2: Creating a chain for the first prompt
chain_question = LLMChain(llm=llm, prompt=prompt_question)
response_question = chain_question.run({})
scientist = response_question.strip()

# Example 3: Updating the template with extracted information
template_fact = """Provide a brief description of {scientist}'s theory of general relativity. Answer:"""
prompt_fact = PromptTemplate(input_variables=["scientist"], template=template_fact)

# Example 4: Creating and running the second prompt in the chain
chain_fact = LLMChain(llm=llm, prompt=prompt_fact)
input_data = {"scientist": scientist}
response_fact = chain_fact.run(input_data)

print("Scientist:", scientist)
print("Fact:", response_fact)
```

This code demonstrates how to use PromptTemplate and LLMChain to create a chain of prompts that extract and build upon information.

## Reference Tables  
| Parameter        | Value/Description               |
|------------------|---------------------------------|
| LLM Model        | GPT-3.5-turbo with temperature=0 |

## Key Takeaways  
1. Use PromptTemplate when you need to create adaptive, iterative prompting systems that build on previous responses.  
2. Extract and incorporate relevant information from each prompt's output into subsequent prompts for refined results.  

## Connects To  
- Relates to natural language processing techniques and iterative refinement in AI systems.