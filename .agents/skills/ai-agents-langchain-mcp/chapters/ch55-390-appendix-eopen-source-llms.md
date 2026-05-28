# Chapter 55: Open Source LLMs

## Core Idea  
This chapter demonstrates how to use Ollama for running open-source large language models (LLMs) in both interactive and server modes, emphasizing proper installation, command execution, and response handling.

## Frameworks Introduced  
- **Ollama Client/Server**: A toolset for executing LLMs via terminal commands or REST APIs.  
  - When to use: For running open-source LLMs locally.  
  - How: Install Ollama, launch the client/server, execute commands/models, and handle responses.

## Key Concepts  
- **Quantized Model**: A reduced-size version of a full model optimized for inference speed.  
- **REST API**: A server-based interface for LLM interactions, not compatible with OpenAI's specifications.  
- **Streaming Response**: Outputs text in real-time; requires setting `stream: false` for complete output.

## Mental Models  
Use Mistral when you need a quantized model optimized for local execution. Think of Ollama as a flexible tool for running various LLMs based on your needs.

## Anti-patterns  
- **Avoid streaming responses**: Use `stream: false` to ensure the full response is received at once, which is crucial for tasks requiring complete output.

## Code Examples  
```bash
ollama run mistral
```
This command launches Ollama with Mistral, downloading a quantized model and processing queries interactively.

## Reference Tables  
| Parameter        | Description                          |
|------------------|---------------------------------------|
| `stream`         | Boolean: true for streaming responses |

## Key Takeaways  
1. Install Ollama to run open-source LLMs locally with ease.  
2. Use the REST API for server-based applications, ensuring proper response handling.  
3. Choose Mistral when a quantized model is sufficient for your needs.

## Connects To  
- Relates to model selection and installation processes in earlier chapters.