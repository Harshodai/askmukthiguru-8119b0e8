# Chapter 63: Supervised Fine-Tuning

## Core Idea
This chapter teaches how to perform supervised fine-tuning using the QLoRA technique with a 4-bit quantized model, enabling efficient training on large datasets.

## Frameworks Introduced
- **QLoRA**: Combines LoRA (Low-Rank Adaptation) for parameter-efficient fine-tuning and 4-bit quantization for memory optimization.
  - When to use: When working with large language models and limited computational resources.
  - How: Apply LoRA decomposition to identify low-rank patterns in model weights, then quantize the remaining parameters to 4 bits.

## Key Concepts
- **LoRA**: Low-Rank Adaptation technique that decomposes model parameters into low-rank matrices for efficient fine-tuning.
- **4-bit Quantization**: Reduces model memory usage by quantizing weights to 4 bits while maintaining computational efficiency.
- **SFTTrainer**: A specialized training class for supervised fine-tuning that integrates LoRA and quantization.

## Mental Models
- Use QLoRA when you need an efficient way to adapt a large language model to a specific task without significant computational overhead. Think of it as a combination of low-rank decomposition (LoRA) and 4-bit quantization, which together help maintain performance while reducing memory usage.

## Anti-patterns
- **Overfitting due to insufficient dataset**: Avoid using fine-tuning on small datasets without proper data augmentation or regularization.
- **Ignoring quantization benefits**: Be cautious not to skip quantization steps as they can significantly reduce model size and training time.
- **Neglecting LoRA integration**: Forgetting to combine LoRA with other techniques may result in suboptimal parameter efficiency.

## Code Examples
```python
from transformers import AutoTokenizer, ConstantLengthDataset, SFTTrainer
from peft import LoraConfig, PeftModel
import torch

# Prepare dataset and model
tokenizer = AutoTokenizer.from_pretrained("facebook/opt-1.3b")
ds = load_dataset("hub://genai360/OpenOrca-1M-train-set")
ds_valid = load_dataset("hub://genai360/OpenOrca-1M-valid-set")

training_args = TrainingArguments(
    output_dir="./OPT-fine_tuned-OpenOrca",
    evaluation_strategy="steps",
    save_strategy="steps",
    num_train_epochs=2,
    eval_steps=2000,
    save_steps=2000,
    logging_steps=1,
    per_device_train_batch_size=8,
    per_device_eval_batch_size=8,
    learning_rate=1e-4,
    lr_scheduler_type="cosine",
    warmup_steps=100,
    gradient_accumulation_steps=1,
    bf16=True,
    weight_decay=0.05,
    ddp_find_unused_parameters=False,
    run_name="OPT-fine_tuned-OpenOrca",
    report_to="wandb"
)

# Initialize model with QLoRA and 4-bit quantization
model = AutoModelForCausalLM.from_pretrained(
    "facebook/opt-1.3b",
    quantization_config=BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16
    ),
    device_map={"": Accelerator().process_index}
)

# Apply LoRA decomposition and quantization
lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)

trainer = SFTTrainer(
    model=model,
    args=training_args,
    train_dataset=ConstantLengthDataset(tokenizer, ds, prepare_sample_text, seq_length=2048),
    eval_dataset=ConstantLengthDataset(tokenizer, ds_valid, prepare_sample_text, seq_length=1024),
    peft_config=lora_config,
    packing=True
)

trainer.train()
```

This code demonstrates how to load and fine-tune a model using QLoRA with 4-bit quantization, showcasing the integration of LoRA decomposition and efficient training techniques.

## Reference Tables

| Parameter                | Value/Setting                          |
|--------------------------|----------------------------------------|
| **Num Epochs**           | 2                                      |
| **Batch Size**           | 8 (per device)                        |
| **Learning Rate**        | 1e-4                                   |
| **Evaluation Steps**     | Every 2000 steps                      |
| **Save Steps**           | Every 2000 steps                      |
| **Gradient Accumulation**| 1                                        |

## Key Takeaways
1. Supervised fine-tuning can significantly improve model performance on specific tasks using QLoRA and quantization.
2. Proper configuration of training arguments is crucial for efficient convergence.
3. Integrating LoRA with quantization optimizes memory usage while maintaining model accuracy.

## Connects To
- Chapter 64: Fine-Tuning Techniques
- Chapter 65: Model Optimization Strategies