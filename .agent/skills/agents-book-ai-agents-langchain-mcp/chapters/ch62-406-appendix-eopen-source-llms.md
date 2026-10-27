# Chapter E: Open Source LLMs

## Core Idea
This chapter demonstrates how to run open-source large language models (LLMs) locally using the Hugging Face Transformers library and LangChain's pipeline interface, providing a foundation for practical applications in research and development.

## Frameworks Introduced
- **Hugging Face Transformers Library**
  - When to use: For fine-grained control over model architecture and backend selection.
  - How: Install backends (PyTorch, TensorFlow, Flax) based on hardware compatibility and framework preferences. Use `pip install transformers` for model loading.

## Key Concepts
- **Model Architecture**: Describes the structure of Mistral Instruct as a transformer-based model with specific layers and attention mechanisms.
- **Tokenization**: The process of converting text into tokens for model input, requiring explicit handling in Transformers.
- **Prompt Template**: A predefined format for generating consistent responses in summarization tasks.
- **max_new_tokens**: A parameter controlling the maximum length of generated outputs.

## Mental Models
- Use Hugging Face Transformers when you need precise control over model architecture and backend optimization. Think of it as a toolset offering flexibility but requiring deeper technical understanding.

## Anti-patterns
- **Avoid using older or unsupported frameworks**: This can lead to compatibility issues, slower performance, and reduced functionality without clear benefits.

## Code Examples
```python
# Example with Hugging Face Transformers (PyTorch backend)
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

model_id = "mistralai/Mixtral-8x7B-Instruct-v0.1"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(model_id, load_in_4bit=True)

text = "Hello my name is"
inputs = tokenizer(text, return_tensors="pt").to(0)
outputs = model.generate(**inputs, max_new_tokens=20)
print(tokenizer.decode(outputs[0], skip_special_tokens=True))
```

```python
# Example with LangChain's Hugging Face Pipeline
from langchain_community.llms import HuggingFacePipeline
from transformers import AutoModelForCausalLM, AutoTokenizer

model_id = "mistralai/Mixtral-8x7B-Instruct-v0.1"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(model_id)

pipe = HuggingFacePipeline.from_model_name(
    model=model,
    tokenizer=tokenizer,
    framework="pt",
    max_new_tokens=50
)

prompt_template = """Question: {question}
Answer: Let's think step by step."""
prompt = PromptTemplate.from_template(prompt_template)
llm_chain = pipe(p prompt)
print(llm_chain.invoke({"question": "How many Greek temples are there in Paestum?"}))
```

## Reference Tables

| **Framework**       | **DL Framework** | **Use Case**                                                                 |
|---------------------|------------------|-----------------------------------------------------------------------------|
| Mistral           | Transformer      | Fine-tuning, custom architectures, and backend optimization.                |
| PyTorch            | Deep Learning     | High-performance computing, dynamic computation graphs.                      |
| TensorFlow         | Tensor Processing | Established ecosystem, production deployment.                               |
| Flax               | JAX-Based        | Compilation for GPU/TPU acceleration.                                     |

## Key Takeaways
1. Running open-source LLMs locally offers flexibility but requires technical expertise and careful configuration.
2. Choosing the right backend depends on hardware compatibility and performance needs.
3. LangChain's Hugging Face pipeline simplifies integration into application workflows.

## Connects To
- Relates to research applications in Chapter 4, demonstrating practical use cases of local LLMs.
```