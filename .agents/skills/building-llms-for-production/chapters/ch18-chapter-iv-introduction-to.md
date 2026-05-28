# Chapter IV: Introduction to Prompting  

## Core Idea  
Prompting is the process of guiding generative AI models to produce desired outputs by providing precise instructions in textual form. It involves translating human goals into structured prompts that leverage AI capabilities effectively.  

## Frameworks Introduced  
- **The 5 Whys**: A technique for digging deeper into root causes or requirements, often used in prompt engineering to refine inputs.  
  - When to use: To uncover underlying issues or desired outcomes by repeatedly asking "Why."  
  - How: Ask "Why" five times to understand the root cause of a problem.  

- **Diagnose the Root Cause**: A method for identifying the primary issue driving a problem, useful in refining prompts to elicit specific responses.  
  - When to use: To pinpoint the main reason behind an issue or desired outcome.  
  - How: Analyze symptoms and underlying causes to determine the root cause of a problem.  

## Key Concepts  
- **Prompting**: The act of providing instructions or questions to AI models for generating outputs.  
- **Prompt Engineering**: The practice of designing and optimizing prompts to maximize AI performance in specific tasks.  
- **OpenAI API Key**: A required credential for integrating OpenAI's generative AI models into applications.  

## Mental Models  
- Use **The 5 Whys** when you need to dig deeper into the root causes of a problem or desired outcome. Think of it as "Why did this happen, why did that happen, and so on."  
- Think of **Diagnose the Root Cause** as identifying the primary issue driving a problem by asking "What is causing this?"  

## Anti-patterns  
- **Over-simplification**: Using broad or vague prompts can lead to irrelevant or incomplete responses. Why it fails: Fails to provide precise instructions, resulting in ambiguous outputs.  
- **Ignoring Context**: Failing to include relevant background information in prompts can result in misaligned or incorrect outputs.  

## Code Examples  
```python
# Example: Story Generation  
import openai  
from langchain.schema import Message  
import os  

os.environ['OPENAI_API_KEY'] = "your-api-key"  
prompt_system = """You are a helpful assistant whose goal is to help write stories."""  
prompt = """Continue the following story. Write no more than 50 words.  
Once upon a time, in a world where animals could speak..."  

response = openai.ChatCompletion.create(  
    model="gpt-3.5-turbo",  
    messages=[  
        { "role": "system", "content": prompt_system },  
        { "role": "user", "content": prompt }  
    ]  
)  

print(response.choices[0]['message']['content'])  
```
This demonstrates how to structure prompts with system and user messages for effective prompting.  

## Reference Tables  
| **Prompting Technique** | **Application** |
|--------------------------|------------------|
| The 5 Whys                | To uncover root causes or desired outcomes by repeatedly asking "Why." |
| Diagnose the Root Cause    | To identify the primary issue driving a problem |

## Key Takeaways  
1. Understand how to structure prompts using system and user messages for effective communication with AI models.  
2. Use **The 5 Whys** to dig deeper into root causes when refining prompts.  
3. Avoid over-simplification and ensure prompts include relevant context to elicit specific responses.  

## Connects To  
- Relates to generative AI capabilities, natural language processing (NLP), and AI safety concepts discussed in later chapters.