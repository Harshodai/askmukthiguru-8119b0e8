# Chapter 19: 1. Zero-Shot Prompting

## Core Idea
This chapter explores prompting strategies for Large Language Models (LLMs), focusing on zero-shot prompting, in-context learning, and few-shot prompting. It provides practical examples using the LangChain framework to illustrate these techniques.

## Frameworks Introduced
- **Zero-Shot Prompting**: A method where models generate outputs without example data or explicit instructions.
  - When to use: Ideal for quick results when extensive training data isn't available.
  - How: The model is prompted directly with a task description, relying on its inherent capabilities.

- **In-Context Learning**: A broader approach that leverages existing information within the prompt to guide the model's output.
  - When to use: Suitable for complex tasks where the model can learn from context rather than explicit examples.
  - How: The prompt includes relevant examples or data, which the model uses to generate outputs.

- **Few-Shot Prompting**: A subset of in-context learning that uses a limited number of examples to guide the model's output.
  - When to use: Appropriate for tasks where similar examples can be provided alongside prompts.
  - How: The prompt includes a few examples, which help the model generalize and produce accurate outputs.

## Key Concepts
- **Prompt Engineering**: The process of crafting effective prompts to guide LLMs toward desired outputs.
- **Zero-Shot Generation**: Producing text without relying on training data or explicit examples.
- **In-Context Examples**: Using existing information within a prompt to assist the model in generating responses.
- **Few-Shot Learning**: Training models with minimal examples to improve their performance on complex tasks.

## Mental Models
- Use zero-shot prompting when you need quick, context-free outputs from an LLM without extensive data or explicit instructions.  
- Think of few-shot prompting as a way to provide limited guidance through examples, enabling the model to generalize better for new tasks.

## Anti-patterns
- **Avoid ambiguous prompts**: Ambiguous questions can lead to inconsistent or irrelevant outputs.
  - Why it fails: Lack of clarity in requirements leads to unpredictable results.

## Code Examples
```python
# Example Few-Shot Prompting Implementation with LangChain
from langchain import PromptTemplate, FewShotPromptTemplate, LLMChain  
from langchain.chat_models import ChatOpenAI  

llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0)  

examples = [
    {"color": "red", "emotion": "passion"},
    {"color": "blue", "emotion": "serenity"},
    {"color": "green", "emotion": "tranquility"}
]  

example_formatter_template = """  
Color: {color}  
Emotion: {emotion}\n\n"""  
example_prompt = PromptTemplate(input_variables=["color", "emotion"], template=example_formatter_template)  

few_shot_prompt = FewShotPromptTemplate(
    examples=examples,
    example_prompt=example_prompt,
    prefix="""Here are some examples of colors and the emotions associated with them:\n\n""",
    suffix=""",
    input_variables=["input"],
    example_separator="\n",
)  

formatted_prompt = few_shot_prompt.format(input="purple")  

chain = LLMChain(llm=llm, prompt=PromptTemplate(template=f"{formatted_prompt}", input_variables=[]))  
response = chain.run({})  

print("Emotion:", response)
```

This code demonstrates how to implement few-shot prompting to associate colors with emotions using a simple template.

## Reference Tables

| Prompting Strategy          | Approach                  | Use Case                          |
|------------------------------|---------------------------|------------------------------------|
| Zero-Shot Prompting         | Generation without examples | Quick, context-free outputs       |
| In-Context Learning          | Leverage existing info    | Complex tasks with inherent data   |
| Few-Shot Prompting          | Use limited examples      | Tasks requiring generalization     |

## Key Takeaways
1. Use zero-shot prompting when you need quick, context-free outputs from an LLM.
2. In-context learning is suitable for complex tasks where the model can learn from existing information within prompts.
3. Few-shot prompting is ideal for tasks where similar examples can be provided alongside prompts to guide the model's output.

## Connects To
- Relates to prompt engineering (Chapter 18) and model adaptability concepts in Chapter 20.