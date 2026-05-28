# Chapter 10: 5 Decoders in Action

## Core Idea
This chapter explores advanced techniques for generating coherent text using large language models (LLMs), focusing on decoding algorithms that enhance text generation quality.

## Frameworks Introduced
- **Greedy Decoding**: Selects the most probable next word at each step.
  - When to use: Simple and efficient when high coherence is needed.
  - How: Always chooses the highest probability word.
- **Beam Search**: Explores multiple paths through the search space.
  - When to use: When diversity in outputs is desired without excessive computation.
  - How: Maintains a set of candidate sequences, expanding each by adding top-k words and pruning lower-scoring sequences.
- **Temperature Sampling**: Adjusts randomness by scaling probabilities.
  - When to use: To balance creativity and coherence.
  - How: Divides log-probabilities by a temperature parameter; higher values increase randomness.
- **Top-k Sampling**: Selects from the top-k most probable words.
  - When to use: To introduce diversity while maintaining focus on high-probability words.
  - How: Typically equivalent to greedy decoding when k=1, increases diversity with larger k.
- **Top-p Sampling (Nucleus Sampling)**: Selects words within a cumulative probability threshold.
  - When to use: To control randomness by focusing on the most probable subset of words.
  - How: Includes all words whose cumulative probability reaches a specified threshold.

## Key Concepts
- **Decoding Algorithms**: Methods for generating text from LLMs, each with trade-offs between creativity and coherence.
- **Prompting**: Crafted input that guides model outputs towards desired results.
- **Temperature Parameter**: Controls randomness in decoding; higher values increase creativity but may reduce coherence.
- **Beam Search Width (k)**: Number of candidate sequences maintained during generation.

## Mental Models
- Use Beam Search when you want to balance exploration and exploitation in text generation.
- Think Greedy Decoding as a simplified version of Beam Search with k=1, suitable for scenarios requiring high coherence but not diversity.
- Consider Temperature Sampling when tuning the model's creativity without significant performance loss.
- Apply Top-k Sampling to introduce controlled diversity while maintaining focus on high-probability words.

## Anti-patterns
- **Over-reliance on Greedy Decoding**: Can lead to repetitive and monotonous text due to its deterministic nature.
- **Ignoring Prompt Structure**: Fails to provide clear guidance, resulting in ambiguous or irrelevant outputs.

## Code Examples
```python
# Example using OpenAI's API for generating text with prompting

from openai import OpenAI

client = OpenAI(api_key='your-api-key')
prompt = "I am planning a trip to Paris. Can you suggest hotels that are close to public transport and have good reviews?"
model = "gpt-4"
temperature = 0.7
max_tokens = 500

def generate_text(prompt, model="gpt-4"):
    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "user", "content": prompt}
        ],
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return chat_completion.choices[0].message.content

print(generate_text(prompt))
```

This code demonstrates how to use OpenAI's API with a prompt, model selection, and temperature tuning. It generates a hotel suggestion in Paris based on user preferences.

## Reference Tables
| Algorithm          | Characteristics                                      |
|--------------------|-------------------------------------------------------|
| Greedy Decoding    | Selects the most probable next word; simple but repetitive. |
| Beam Search        | Explores multiple paths; balances diversity and coherence.  |
| Temperature       | Controls randomness by scaling probabilities.           |
| Top-k Sampling     | Limits to top-k words, increasing diversity with k.      |
| Top-p Sampling     | Focuses on cumulative probability threshold.          |

## Key Takeaways
1. Use Beam Search when you want a balance between creativity and coherence.
2. Tune temperature settings to control randomness in outputs.
3. Implement top-k sampling for controlled diversity while maintaining focus.
4. Craft effective prompts to guide LLMs towards desired results.

## Connects To
- Relates to encoder-decoder models, prompting strategies, and model evaluation techniques discussed earlier in the chapter.