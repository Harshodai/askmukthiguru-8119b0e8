# Chapter 11: 7. Booking Tips

## Core Idea
The chapter emphasizes leveraging structured prompts to enhance AI-generated descriptions of Paris hotels, ensuring clarity and coherence through zero-shot, few-shot, and chain-of-thought prompting.

## Frameworks Introduced
- **Zero-Shot Prompting**: Uses explicit instructions without examples.
  - When to use: When the model must infer from minimal guidance.
  - How: Directs the AI to generate text based on partial information.
  
- **Few-Shot Prompting**: Includes a few examples within the prompt.
  - When to use: When guiding the model with clear precedents.
  - How: Provides explicit context for structured responses.

- **Chain-of-Thought Prompting**: Encourages step-by-step reasoning.
  - When to use: For complex problem-solving tasks like hotel descriptions.
  - How: Guides the AI to break down problems and explain its reasoning.

## Key Concepts
- **Location Considerations**: Proximity to landmarks, neighborhoods, and transportation hubs.
- **Price Ranges**: Budget, mid-range, luxury options with specific value propositions.
- **Popular Areas**: Le Marais (entertainment), Montmartre (artistic heritage), Sacré-Cœur (religion).

## Mental Models
- Use zero-shot prompting when you need concise descriptions without examples.
- Apply few-shot prompting to add context and structure to AI outputs.
- Employ chain-of-thought prompting for detailed, logical hotel descriptions.

## Anti-patterns
- **Over-reliance on hallucinations**: Without structured prompts, AI may generate unreliable information.

## Code Examples
```python
def generate_text(prompt):
    few_shot_examples = """Example 1:
New York hotels: The Plaza offers luxury with modern amenities.
Example 2:
Paris hotels: The Ritz has historic elegance and prime location.
"""
    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "user", "content": f"{few_shot_examples}\n{prompt}"}
        ],
        model=model,
        temperature=0.7,
        max_tokens=200,
    )
    return chat_completion.choices[0].message.content
```

## Reference Tables

| **Prompt Type**       | **Use Case**                     |
|-----------------------|------------------------------------|
| Zero-Shot Prompting   | Basic hotel description          |
| Few-Shot Prompting     | Hotel comparison                   |
| Chain-of-Thought      | Complex hotel features           |

## Key Takeaways
1. Use structured prompts to enhance AI-generated descriptions.
2. Combine prompting techniques for optimal results.
3. Prioritize clarity and coherence in hotel descriptions.

## Connects To
- Relates to location considerations, price ranges, and transportation access.