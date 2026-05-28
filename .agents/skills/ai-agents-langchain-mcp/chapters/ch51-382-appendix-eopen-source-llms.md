# Chapter 51: E Open source LLMs

## Core Idea  
Quantization enables running large language models locally by reducing their size and inference speed while maintaining acceptable accuracy. This allows experimentation with high-capacity models using modest hardware resources.

## Frameworks Introduced  
- **OpenAI REST API Compatibility**: Simplifies testing multiple engines with minimal code changes, supporting quick adoption of different inference engines.

## Key Concepts  
- **OpenAI Public API Endpoint**: The `chat/completions` endpoint for making requests to OpenAI's servers.  
- **GPT-4o-mini**: A specific model version optimized for local use with reduced size and faster inference.

## Mental Models  
Use quantization when you need to experiment with large models locally, balancing speed and accuracy as required by your application.

## Anti-patterns  
Avoid using quantized models if you prioritize accuracy over performance or if you fail to properly integrate the OpenAI REST API into your codebase.

## Code Examples  
```python
import os
import requests

def call_openai_api(prompt):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {os.getenv("OPENAI_API_KEY")}'
    }
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{
            "role": "system",
            "content": "You are a helpful AI assistant."
        }, {
            "role": "user", 
            "content": prompt
        }],
        "temperature": 0.7
    }
    
    response = requests.post(url, headers=headers, json=payload)
    return response.json()
```

This code demonstrates how to make an API request using the OpenAI Python library and `curl`, showcasing minimal modifications needed for testing different engines.

## Reference Tables  
| **Inference Engine** | **Hardware Requirements** | **Quantization Technique** | **Model Size Reduction** |
|-----------------------|----------------------------|------------------------------|---------------------------|
| Llama-70B             | 140 GB RAM, A100 GPU        | Post-Training Quantization   | 3.9 GB                    |
| GPT-4o-mini           | Modest laptops               | 4-bit Normal Float            | 3.9 GB (vs. original size) |

## Key Takeaways  
1. Use quantization to reduce model size and improve inference speed for local experimentation.
2. Ensure OpenAI REST API compatibility when selecting an inference engine to simplify testing and deployment.
3. Evaluate engine performance based on response time, accuracy, and hardware utilization.

## Connects To  
- Chapters on model optimization techniques
- Discussions on local development workflows