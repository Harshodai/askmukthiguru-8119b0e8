# Chapter 56: E Open source LLMs

## Core Idea
This chapter introduces Mistral as an open-source alternative to GPT-4 for local inference engines, providing insights into its architecture and usage.

## Frameworks Introduced
- **Mistral**: An open-source large language model framework.
  - When to use: When seeking a lightweight, cost-effective option for text generation tasks without relying on paid services or waiting for updates.
  - How: Mistral can be accessed via the Ollama Python library and integrated with tools like LangChain.

## Key Concepts
- **Open source LLMs**: Free and customizable large language models developed by the community.
- **Mistral**: A high-performance open-source model based on the GPT architecture.
- **Ollama**: A Python client for locally running and querying open-source LLMs like Mistral.
- **LangChain**: A framework that integrates with local LLMs, enabling asynchronous execution and integration into larger applications.

## Mental Models
- Use Mistral when you need a lightweight, cost-effective option for text generation tasks without relying on paid services or waiting for updates.

## Anti-patterns
- **Over-reliance on Mistral**: Avoid using Mistral exclusively without considering other models like GPT-4, as it may not be suitable for all use cases.

## Code Examples
```
import ollama

response = ollama.chat(model='mistral', messages=[    { "role": "system", "content": "You are a helpful AI assistant" },    { "role": "user", "content": "How many Greek temples are in Paestum?" }
])
print(response['message']['content'])
```
- **What it demonstrates**: Using the Ollama Python library to access Mistral and perform inference.

## Reference Tables
| Model | Architecture | Parameters (B) | Cost |
|-------|--------------|-----------------|------|
| GPT-4 | Transformer   | 175B            | High cost |
| Mistral | Transformer | 30B             | Free |

## Key Takeaways
1. Use Mistral when you need a lightweight, open-source option for text generation.
2. Consider integrating with Ollama and LangChain for seamless API access.
3. Avoid over-reliance on Mistral alone; evaluate other models like GPT-4 based on your specific needs.

## Connects To
- Relates to concepts in chapters discussing model architectures, API usage, and cost-effectiveness considerations.