# Chapter 52: E Open source LLMs

## Core Idea
This chapter explains how to run open-source large language models (LLMs) locally by adapting requests to local inference engines.

## Frameworks Introduced  
- **OpenAI Library**:  
  - When to use: For leveraging the OpenAI API in Python.  
  - How: Create a virtual environment, install the library with `pip install openai`, and use the client for API calls.  

## Key Concepts  
- **Model Name Convention**: Models follow conventions like `mistralai/Mistral-7B-v0.3`.  
- **Port Adjustment**: Local servers often default to different ports; check documentation for correct port number.  
- **Request Headers**: Use "Content-Type: application/json" and omit OpenAI API key from headers.

## Mental Models  
- Use Mistral-7B-v0.3 when running local inference engines that support this model format.  
- Think of adjusting the port number as changing the communication channel for the LLM.  

## Anti-patterns  
- **Avoid Not Adjusting Settings**: Failing to change ports or models can lead to connection issues.  
- **Avoid Misusing Models**: Using external API calls without understanding local setup requirements.

## Code Examples  
```python
import getpass
from openai import OpenAI

OPENAI_API_KEY = getpass.getpass('Enter your OPENAI_API_KEY')
client = OpenAI(api_key=OPENAI_API_KEY)

completion = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "You are a helpful AI assistant."},
        {"role": "user", "content": "How many Greek temples are there in Paestum?"}
    ],
    temperature=0.7
)

print(completion.choices[0].message.content)
```
- **What it demonstrates**: Step-by-step API call setup and model usage for local inference.

## Reference Tables  
| Model Name Convention | Example Format       |
|----------------------|-----------------------|
| Hugging Face Models   | mistral/Mistral-7B    |
| Mistral AI Models   | mistralai/Mistral-7B-v0.3 |

| Local Engine | Default Port | Example Model Name               |
|--------------|--------------|----------------------------------|
| Fast.ai       | 5678          | mistralai/Mistral-7B-v0.3       |
| Hugging Face  | 8000         | mistral/Mistral-7B             |

## Key Takeaways  
1. Use Mistral-7B-v0.3 when running local inference engines that support this model format.  
2. Always adjust the port number and model name based on the engine's documentation.  
3. Avoid external API calls without proper local setup understanding.

## Connects To  
- Relates to chapters on running open-source LLMs locally or considering alternatives like Mistral for deployment.