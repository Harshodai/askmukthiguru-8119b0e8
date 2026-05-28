# Chapter 23: Introduction to LangChain & LlamaIndex

## Core Idea
This chapter introduces LangChain as a powerful framework for building applications powered by Large Language Models (LLMs), emphasizing its role in simplifying complex tasks and integrating retrieval-augmented generation.

## Frameworks Introduced
- **LangChain**: An open-source framework designed to streamline the development of LLM-powered applications by abstracting away complexity through tools like Prompts, Output Parsers, Retrievers, and Agents. It supports advanced features such as LangGraph for stateful multi-agent systems and LangServe for API deployment.

## Key Concepts
- **LLM**: A large language model capable of understanding and generating human-like text.
- **Prompt Template**: A structured prompt used to guide LLM interactions, enhancing control over conversations.
- **Output Parser**: Converts an LLM's raw response into a more usable format.
- **Retriever**: Retrieves relevant data from external sources for LLMs.

## Mental Models
- Use LangChain's tools when you need to structure prompts or integrate retrieval-augmented generation. Think of LangChain as your go-to framework for building efficient, scalable applications with LLMs.

## Anti-patterns
- **Over-reliance on hallucinations**: Avoid using LLMs without integrating retrieval-augmented generation techniques like RAG to mitigate potential inaccuracies.

## Code Examples
```python
from langchain.chat_models import ChatOpenAI  
from langchain.prompts.chat import ( 
    ChatPromptTemplate , 
    SystemMessagePromptTemplate , 
    HumanMessagePromptTemplate , 
) 

# Example for movie information retrieval
chat = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0)
template = "You are an assistant that helps users find information about movies."
system_message_prompt = SystemMessagePromptTemplate.from_template(template)
human_template = "Find information about the movie {movie_title}."
human_message_prompt = HumanMessagePromptTemplate.from_template(human_template)
chat_prompt = ChatPromptTemplate.from_messages([system_message_prompt, human_message_prompt])
response = chat(chat_prompt.format_prompt(movie_title="Inception").to_messages())
print(response.content)
```

This code demonstrates using LangChain to format prompts and retrieve information about a movie.

## Reference Tables
| Framework         | Purpose                                      |
|-------------------|---------------------------------------------|
| LangChain          | Simplifies building LLM applications       |
| RAG               | Reduces hallucinations with retrieval      |

## Key Takeaways
1. Use LangChain's tools for structured prompts and retrieval-augmented generation.
2. Leverage agents for complex tasks, combining multiple components like prompts, retrievers, and tools.
3. Avoid over-reliance on LLMs without integrating RAG techniques.

## Connects To
- Relates to concepts in "RAG Methods" and "Agents & Tools" sections within the chapter.