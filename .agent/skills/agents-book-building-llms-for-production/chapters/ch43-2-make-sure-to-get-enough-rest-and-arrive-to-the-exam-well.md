# Chapter 43: 2. Make sure to get enough rest and arrive to the exam well-

## Core Idea
This chapter emphasizes the importance of ethical AI responses by introducing the Constititional Chain framework, which ensures language models adhere to predefined principles like Politeness and Objectivity.

## Frameworks Introduced
- **ConstitutionalChain**: A framework that integrates ethical principles into AI responses, ensuring compliance with rules like Politeness and Objectivity.
  - When to use: When developing AI systems that require ethical and consistent outputs.
  - How: By chaining models with constitutional principles to revise and improve responses.

## Key Concepts
- **Constitutional Principle**: A rule-based system for guiding AI behavior, ensuring outputs align with predefined values like politeness and objectivity.
- **Critique Request**: A prompt sent to the model to assess and improve its output based on ethical standards.
- **Revise Request**: A prompt sent after critique to refine and correct the model's response.

## Mental Models
- Use the Constititional Chain when you need to ensure AI responses are both ethical and high-quality. Think of it as a system that continuously evaluates and improves outputs to meet set standards.

## Anti-patterns
- **Avoiding Negative Responses**: Do not allow models to generate offensive or harmful content, even if technically correct.
  - Why it fails: Negative responses can damage brand reputation and harm user trust.

## Code Examples
```python
from langchain.chains.constitutional_ai.base import ConstitutionalChain  
from langchain.chains.constitutional_ai.models import ConstitutionalPrinciple  

# Define a Polite Principle  
polite_principle = ConstitutionalPrinciple(  
    name="Polite Principle", 
    critique_request="The assistant should be polite to the users and not use offensive language.", 
    revision_request="Rewrite the assistant's output to be polite."  
)

# Create an Identity Chain for QA responses  
prompt_template = """Rewrite the following text without changing anything: {text}"""  
identity_prompt = PromptTemplate(template=prompt_template, input_variables=["text"])  
identity_chain = LLMChain(llm=llm, prompt=identity_prompt)  

# Create a Constitutional Chain using RetrievalQA  
constitutional_chain = ConstitutionalChain.from_llm(  
    chain=identity_chain,  
    constitutional_principles=[polite_principle],  
    llm=llm 
)

# Use the chain to revise an offensive response  
response = d_response_not_ok["answer"]  # Offensive response from model
revised_response = constitutional_chain.run(text=response)
print("Unchecked response:", response)  
print("Revised response:", revised_response)
```

## Reference Tables
| Principle        | Description                                                                 |
|------------------|--------------------------------------------------------------------------|
| Polite Principle | Ensures responses are polite and respectful to users.                   |
| Objectivity       | Ensures responses are factually accurate and unbiased.                 |

## Key Takeaways
1. Use the Constititional Chain framework to ensure ethical AI responses.
2. Always revise negative or offensive outputs using the ConstitutiveChain's critique and revision process.
3. Prioritize politeness and objectivity in all AI-generated content.

This chapter bridges the gap between technical AI development and ethical considerations, providing a robust framework for creating trustworthy AI systems.