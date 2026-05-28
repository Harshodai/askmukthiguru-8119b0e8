# Chapter E: Open Source LLMs

## Core Idea
This chapter teaches you how to enable local inference with open-source large language models (LLMs) using llamafile and LM Studio. It provides actionable guidance on setting up and interacting with these models for various applications.

## Frameworks Introduced
- **llamafile**: Enables running prebuilt LLMs locally, supporting models like Mistral, Gemma, and Phi.
  - When to use: For running specific prebuilt LLMs directly on your system.
  - How: Download the model file, set permissions, run it, and access via a web interface or API.

- **LM Studio**: A tool for managing GGUF models, integrating with Hugging Face for selection and downloading.
  - When to use: For selecting and downloading quantized models like Mistral in 2-bit format.
  - How: Use the model search interface to find and download models, then interact via chat or API.

## Key Concepts
- **OpenAI API**: Accessible through programming languages like Python using LangChain or curl for specific LLMs.
- **Quantization**: Reduces model size but lowers performance fidelity; e.g., 2-bit quantization in Mistral offers low fidelity and high speed.
- **Server Setup**: Can run models directly (server mode) or access via a web interface.

## Mental Models
- Use llamafile when you need to run specific prebuilt LLMs locally for inference tasks.
- Think of LM Studio as a tool to manage model versions, especially useful for quantized formats like 2-bit Mistral.

## Anti-patterns
- **Avoid not setting up the server correctly**: Ensure proper port settings (e.g., 8080) and permissions for successful model access.

## Code Examples
```python
# Example of starting a server with llamafile
from llamafile import Llama

llama = Llama()
llama.run_server(port=8080)
```

This demonstrates initializing and running a local LLM server using llamafile, accessible at `http://localhost:8080`.

## Reference Tables
| Model      | Quantization | Fidelity       | Use Case                          |
|------------|---------------|----------------|-------------------------------------|
| Mistral    | 2-bit          | Low            | High-performance inference tasks     |
| Phi        | None           | High           | General-purpose LLM use cases       |

## Key Takeaways
1. Enable local LLM access using llamafile and LM Studio for various applications.
2. Leverage quantized models like Mistral's 2-bit version for faster performance.
3. Set up server modes appropriately for direct model execution or web interface access.

## Connects To
- Relates to understanding open-source NLP tools and their deployment options in local environments.