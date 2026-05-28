# Chapter 59: 400 APPENDIX E Open source LLMs

## Core Idea  
This chapter demonstrates how to set up and utilize open-source large language models (LLMs) using a custom inference engine and Docker-based containerization.

## Frameworks Introduced  
- **LocalAI**: A Go-based high-level inference engine designed to run OpenAI-compatible REST API LLMs on consumer hardware, supporting quantized models like Mistral-7B.  
  - When to use: When you need to deploy an LLM locally without relying on cloud services.  
  - How: Routes OpenAI-like API calls to backend engines such as llama.cpp or vLLM.

## Key Concepts  
- **OpenAI REST API Endpoints**: Access points for interacting with LLMs, including `/v1/chat/completions`, `/v1/completions`, and `/v1/embeddings`.  
- **Rolling Window Context Overflow Policy**: A mechanism to manage context in local inference engines.  

## Mental Models  
Use LocalAI when you need to run an LLM locally on consumer hardware or GPUs, especially with quantized models like Mistral-7B.

## Anti-patterns  
- **Avoid using slow, inefficient containers**: Using Docker without optimizations (e.g., `-f`, `-itk`, `-swx`) can lead to suboptimal performance.  

## Code Examples  
```bash
docker run -ti -p 8080:8080 --gpus all localai/localai:v2.7.0-cublas-cuda12-core mistral-openorca
```
- **What it demonstrates**: Efficient deployment of Mistral-7B on CUDA-enabled GPUs using LocalAI.

## Reference Tables  
| Parameter        | Value/Description                                                                 |
|------------------|-----------------------------------------------------------------------------------|
| Model Name       | Mistral-OpenOrca                                                                 |
| Container Image  | `localai/localai:v2.7.0-cublas-cuda12-core`                                         |
| Deployment Option | `-gpus all` during Docker container run                                                |

## Key Takeaways  
1. Use LocalAI to deploy Mistral-7B on CUDA-enabled GPUs for efficient inference.  
2. Leverage Docker containers with optimized flags for better performance.  

## Connects To  
- Relates to broader concepts of LLM deployment and inference engine selection.