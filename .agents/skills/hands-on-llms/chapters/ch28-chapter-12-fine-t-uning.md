# Chapter 28: Chapter 12. Fine-Tuning

## Core Idea
The chapter teaches how to adapt pretrained language models for specific tasks using three main steps: pretraining, supervised fine-tuning (SFT), and preference tuning (PF). These methods allow models to follow instructions and align outputs with desired preferences efficiently.

## Frameworks Introduced
- **Supervised Fine-Tuning (SFT)**:
  - When to use: When you need a model to follow specific instructions or tasks.
  - How: Adapt the base model using labeled data where inputs have additional labels, adjusting parameters based on these labels.

- **Preference Tuning (PF)**:
  - When to use: To align model outputs with desired preferences or behaviors.
  - How: Fine-tune models post-SFT to ensure they follow specific task-oriented patterns without retraining from scratch.

## Key Concepts
- **Language Modeling**: Training a model on massive datasets to predict next tokens, forming the base for any LLM.
- **Supervised Fine-Tuning (SFT)**: Using labeled data to adapt the base model to follow instructions or complete tasks.
- **Preference Tuning (PF)**: Adjusting fine-tuned models to align outputs with specific preferences or behaviors.

## Mental Models
Use SFT when you need a model to perform task-specific functions, and PF when you want to ensure outputs meet particular behavioral criteria. Avoid relying solely on inefficient methods like full pretraining without utilizing LoRA or QLoRA for efficiency.

## Anti-patterns
- **Avoid not using efficient fine-tuning techniques**: Using traditional methods without employing LoRA or QLoRA can lead to performance drops while wasting resources.

## Code Examples
```python
from peft import LoraConfig, prepare_model_for_kbit_training, get_peft_model

# Example of SFT and PF configuration
peft_config = LoraConfig(
    lora_alpha=32,
    lora_dropout=0.1,
    r=64,
    bias="none",
    task_type="CAUSAL_LM",
    target_modules=["k_proj", "gate_proj", "v_proj", "up_proj", "q_proj", "o_proj", "down_proj"]
)

model = prepare_model_for_kbit_training(model)
model = get_peft_model(model, peft_config)
```
This demonstrates how to configure LoRA for efficient fine-tuning.

## Reference Tables
| Framework | Description | When to Use       |
|-----------|--------------|-------------------|
| SFT        | Adapts base model with labeled data | Follow instructions or complete tasks |
| PF         | Aligns outputs with preferences   | Specific task behavior alignment |

## Key Takeaways
1. Use SFT when you need a model to follow specific instructions.
2. Use PF for aligning model outputs with desired behaviors efficiently.
3. Employ LoRA or QLoRA for efficient fine-tuning instead of traditional methods.

## Connects To
- Relates to chapter 10 on language modeling and chapter 11 on pretraining as foundational steps in this process.