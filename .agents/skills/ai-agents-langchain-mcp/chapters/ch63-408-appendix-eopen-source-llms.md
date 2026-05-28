# Chapter 63: Open Source LLMs

## Core Idea
This chapter demonstrates how to integrate open-source large language models (LLMs) into an application using OpenAI-compatible APIs, focusing on minimizing code changes and highlighting performance trade-offs between local and cloud-based solutions.

## Frameworks Introduced
- **LM Studio**: An open-source framework offering OpenAI-compatible requests.
  - When to use: When seeking a lightweight, flexible alternative to native Python bindings like GPT4All.
  - How: By setting up an LM Studio server and routing requests through its API endpoints.

## Key Concepts
- **OpenAI-Compatible Requests**: Requests routed through specific URLs with the appropriate API key format.
- **Base URL**: The endpoint used for communication with the LLM, typically `http://localhost:port_number/v1`.
- **Model Names**: Identifiers for different LLM versions (e.g., "gpt-4o-mini", "mistral").

## Mental Models
- Use LM Studio when you need an OpenAI-compatible solution without rewriting code.
- Think of local LLMs as a cost-effective option but be aware of performance limitations.

## Anti-patterns
- **Avoid sticking to expensive cloud-based solutions**: Unless necessary for advanced functionality, consider using free or budget-friendly alternatives like local LLMs.

## Code Examples
```python
def get_llm(is_llm_local=False):
    port_number = '8080'
    if is_llm_local:
        client = OpenAI(
            base_url=f'http://localhost:{port_number}/v1',
            model='mistral'
        )
    else:
        client = OpenAI(openai_api_key=openai_api_key, model="gpt-4o-mini")
    return client
```
**What it demonstrates**: Modifying the `get_llm()` function to switch between local and cloud-based LLMs based on a flag.

## Reference Tables

| Framework      | Port Number | API Key Needed? | Base URL Example                          | GPU Support Required |
|----------------|-------------|-----------------|--------------------------------------------|----------------------|
| LM Studio      | 8080        | No              | `http://localhost:8080/v1`               | No                   |
| GPT4All        | Varies      | Yes             | As configured by the user                | May require GPU     |

## Key Takeaways
1. Use LM Studio when you need an OpenAI-compatible solution without extensive code changes.
2. Modify your application minimally to integrate a local LLM for flexibility and cost-effectiveness.
3. Be aware of performance limitations with local LLMs, especially on CPUs.
4. Consider using a quantized local LLM for development but recognize it may not meet production requirements.
5. Optimize performance by deploying LM Studio on hardware with an NVIDIA GPU or using advanced inference engines like vLLM.

## Connects To
- Relates to chapters discussing model selection and infrastructure planning in technical applications.