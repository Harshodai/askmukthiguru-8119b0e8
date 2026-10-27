# Chapter 20: Role Prompting

## Core Idea
Role prompting is a technique that instructs an LLM to assume a specific role, enabling it to generate responses tailored to that identity for effective task execution.

## Frameworks Introduced
- **Role Prompting**: A method where the prompt explicitly states the assumed role (e.g., "As a futuristic robot band conductor") before asking the AI to perform a task. This ensures the LLM generates outputs aligned with the specified role.
  - When to use: When you need an AI to assume a specific identity for generating tailored responses.
  - How: Define the role in the prompt, provide context, and structure the request clearly.

## Key Concepts
- **Precise Directions**: Clear instructions given to the LLM about what to do.
- **Specificity**: Providing detailed information about the task or theme to guide the AI's response.
- **Creativity Promotion**: Encouraging the LLM to generate imaginative and creative responses without restricting formats or styles.
- **Task Focus**: Concentrating solely on completing the task, avoiding distractions from unrelated subjects.

## Mental Models
- Use role prompting when you need an AI to assume a specific identity for generating tailored responses. This helps in creating consistent and relevant outputs by aligning the LLM's response with the defined role.

## Anti-patterns
- **Integrating multiple tasks into one prompt**: This can confuse the model, leading to less effective outputs as it struggles to focus on each task individually.

## Code Examples
```python
from langchain import PromptTemplate, LLMChain  
from langchain.chat_models import ChatOpenAI  

# Initialize LLM  
llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0) 

template = """ 
As a futuristic robot band conductor, I need you to help me come up with a
song title.  
What's a cool song title for a song about {theme} in the year {year}? 
""" 

prompt = PromptTemplate(  
    input_variables=["theme", "year"], 
    template=template,  
)  

# Create the LLMChain for the prompt  
llm_chain = LLMChain(llm=llm, prompt=prompt)  

input_data = {"theme": "interstellar travel", "year": "3030"}  

response = llm_chain.run(input_data)  

print("AI-generated song title:", response)  
```
- **What it demonstrates**: How to use parameterized prompts in LangChain to generate tailored responses based on specific inputs.

## Reference Tables
| Parameter        | Description                                                                 |
|------------------|-----------------------------------------------------------------------------|
| `theme`          | The theme or subject for which the AI generates a song title.              |
| `year`           | The year specified, influencing the song title's style and theme.         |

## Key Takeaways
1. Use role prompting when you need an AI to assume a specific identity for generating tailored responses.
2. Ensure prompts are precise, specific, and focused on the task at hand to elicit effective outputs.
3. Encourage creativity by allowing the LLM to produce imaginative responses without restrictive formats or styles.
4. Avoid overloading prompts with multiple tasks to maintain clarity and effectiveness.

## Connects To
- Effective prompting strategies discussed in previous chapters.