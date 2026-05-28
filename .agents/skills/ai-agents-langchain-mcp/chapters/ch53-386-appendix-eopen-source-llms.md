# Chapter E: Open source LLMs

## Core Idea  
Local inference engines enable running open-source large language models on consumer hardware by hosting the model locally and handling client requests through native bindings.

## Frameworks Introduced  
- **Ollama**: A user-friendly tool built on llama.cpp, offering a desktop application for running local LLMs.  
  - When to use: For users comfortable with graphical interfaces and need simplicity.  
  - How: Instantiates an Ollama server, hosts the model, and interacts via HTTP requests.  

- **llama.cpp**: A high-performance inference engine supporting various hardware backends (e.g., Linux, Windows, Raspberry Pi).  
  - When to use: For performance-critical applications requiring low-latency inference.  
  - How: Compiles models with quantization (e.g., 4-bit for GPUs) and runs them natively.  

- **vLLM**: An open-source library supporting multiple backend engines like llama.cpp, offering flexibility in deployment.  
  - When to use: For developers needing a lightweight, extensible solution.  
  - How: Integrates with custom models or existing inference engines via vLLM's bindings.  

## Key Concepts  
- **Local Inference Engine**: A tool that hosts and runs open-source LLMs locally on consumer hardware, bypassing external APIs.  
- **OpenAI REST API**: A standardized interface for interacting with OpenAI's cloud-based LLMs, often used in conjunction with inference engines.  
- **Model Quantization**: Technique (e.g., 4-bit) to reduce model size and improve inference speed on specific hardware.  

## Mental Models  
- Use Ollama when you need a simple, user-friendly desktop application for running local LLMs.  
- Think of llama.cpp as the foundation for high-performance inference engines like Ollama or vLLM.  

- **What to avoid**: Monolithic setups without proper engine compatibility checks or deployment planning.  

## Code Examples  
```python
from langchain_openai import ChatOpenAI

port_number = '8080'
llm = ChatOpenAI(openai_api_base=f'http://localhost:{port_number}/v1')
response = llm.invoke("How many Greek temples are there in Paestum?")
print(response.content)
```

This code demonstrates using LangChain's OpenAI wrapper to interact with a local inference engine hosted via vLLM or Ollama.

## Reference Tables  
| Framework | Port Number | Model Name Convention | Example Use Case |
|-----------|-------------|-----------------------|------------------|
| Ollama    | 8080         | Depends on engine     | Desktop application |
| llama.cpp | 8080         | quantized models      | High-performance   |
| vLLM      | 8080         | Custom or pre-trained  | Flexible deployment|

## Key Takeaways  
1. Use Ollama for its simplicity and desktop-friendly interface.  
2. Opt for llama.cpp when high performance is critical.  
3. Choose vLLM for extensibility and custom model support.  

## Connects To  
- Relates to Chapter D: Running OpenAI LLMs on the Cloud