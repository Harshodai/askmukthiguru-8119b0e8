# Chapter 7: Chapter 6

## Core Idea
This chapter teaches you how to craft effective prompts by understanding their structure, using techniques like the Sandwich Technique, and selecting appropriate document formats (e.g., advice conversations or analytic reports) for your task.

## Frameworks Introduced
- **Sandwich Technique**: A method for structuring prompts with an introduction, context, and refocus.  
  - When to use: When you need a prompt that clearly states the problem and guides the model's response.
  - How: Start with an introduction explaining the main question, add context elements, and end with a refocus statement.

- **Inception Method**: A technique where you dictate part of the answer upfront.  
  - When to use: With completion models to ensure compliance with your instructions.
  - How: Provide the beginning of your answer for the model to complete.

- **Advice Conversation**: A format where two parties exchange information, often used for chat models.  
  - When to use: For complex interactions or when you want a conversational prompt structure.
  - How: Use questions and answers to guide the model's response.

- **Analytic Report**: A structured document suitable for tasks requiring detailed analysis (e.g., market research).  
  - When to use: For tasks that require clear, logical reasoning and organization.
  - How: Include sections like introduction, analysis, and conclusion to guide the model's output.

## Key Concepts
- **Context Window Size**: The number of elements in a prompt; too long can reduce effectiveness.  
- **Lost Middle Phenomenon**: Context elements near the middle of a prompt have less impact than those at the ends.  
- **Refocus Transition**: A statement that directs the model to provide a specific type of response.

## Mental Models
- Use the Sandwich Technique when you need a prompt that clearly states the problem and guides the model's response.
- Think of Inception as a way to ensure compliance with your instructions, especially with completion models.
- Consider using an Advice Conversation for complex interactions or chat-based prompts.
- Opt for an Analytic Report when you need structured, detailed outputs.

## Anti-patterns
- **Overcomplicated Prompts**: When the prompt is too long or unclear, leading to ineffective communication.  
  - What to avoid: Unclear instructions and excessive context that hinders focus.

## Code Examples
```python
# Example of a Sandwich Prompt
context = """Introduction: Explain the main question clearly.
Context: List relevant details concisely.
Refocus: Direct the model's response explicitly."""
full_prompt = f"{''.join(['[', ']', sep=';'])}{context}"
```

## Reference Tables

| Document Type         | Use Case                          | Example Structure                     |
|-----------------------|------------------------------------|--------------------------------------|
| Advice Conversation   | Chat with an expert                | "What should I do about X?"          |
| Analytic Report        | Market analysis                    | Introduction: Background; Analysis: Data evaluation; Conclusion: Recommendations |
| Sandwich Technique     | Problem-solving                   | [Introduction] What's the solution? ; [Context] Details here ; [Refocus] Provide answer |

## Key Takeaways
1. Use the Sandwich Technique to structure your prompts for clarity and effectiveness.
2. Choose appropriate document formats based on your task requirements.
3. Avoid overcomplicating prompts by keeping instructions clear and concise.

## Connects To
- Chapter 5: Understanding Context and Dynamic Constraints  
- Chapter 8: Advanced Prompt Engineering Techniques