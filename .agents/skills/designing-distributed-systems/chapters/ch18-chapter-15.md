# Chapter 18: CHAPTER 15

## Core Idea
AI inference is about efficiently serving pre-trained or fine-tuned AI models for interactive applications with low latency and high accuracy.

## Frameworks Introduced
- **ONNX (Open Neural Network Exchange)**:
  - When to use: When working with pre-trained models that need to be deployed on non-GPU environments.
  - How: ONNX provides a standardized format for models, enabling deployment across different frameworks like TensorFlow, PyTorch, and native GPU execution.

## Key Concepts
- **AI Model**: A mathematical representation of knowledge encoded in neural networks, used for inference tasks.
- **Prompt Engineering**: The process of crafting input prompts to guide AI responses toward desired outputs by adding context or instructions.
- **Hugging Face Model Hub**: An open-source platform providing access to pre-trained models and tools for easy integration into applications.

## Mental Models
- Use ONNX when you need to deploy a model on non-GPU environments. Think of ONNX as the universal language for AI models, enabling cross-framework compatibility.

## Anti-patterns
- **Overfitting to Specific Datasets**: Avoid creating monolithic models that perform well only on training data and fail in real-world scenarios.
  - What to avoid: Relying solely on pre-trained models without considering their generalizability to new contexts or user-specific needs.

## Code Examples
```python
# Example of wrapping an ONNX model for inference

import numpy as np
from onnxruntime import InferenceSession

def load_model(model_path):
    session = InferenceSession(model_path)
    return session

def infer(input_features):
    input_dict = {session.get_input_details()[0].name: input_features}
    outputs = session.run(None, input_dict)
    return outputs[0]

# Usage
model_session = load_model("path/to/model.onnx")
input_data = np.array([1.0, 2.0, 3.0], dtype=np.float32).reshape(1, -1)
result = infer(input_data)
```

This code demonstrates loading an ONNX model and performing inference using ORT, a popular runtime for deep learning models.

## Reference Tables
| Framework | Model Format | Deployment Compatibility |
|----------|--------------|-------------------------|
| ONNX     | None         | Cross-framework       |
| TensorFlow Lite | .tflite      | Mobile device support  |
| PyTorch  | None         | GPU/CPU/CUDA support    |

## Key Takeaways
1. Choose the appropriate framework (e.g., ONNX for non-GPU environments) based on your deployment needs.
2. Leverage prompt engineering to provide context-specific responses in RAG applications.
3. Test AI models across diverse prompts to ensure statistical quality and generalizability.

## Connects To
- Relates to chapters on model training, fine-tuning, and application architecture for AI development.