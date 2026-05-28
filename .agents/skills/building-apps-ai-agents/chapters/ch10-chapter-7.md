```markdown
# Chapter 7: Learning in Agentic Systems

## Core Idea
The chapter explores how to enhance intelligent agents through learning, focusing on two main approaches: nonparametric learning techniques like Reflexive Learning and Prompt Engineering, and parametric fine-tuning methods such as Fine-Tuning Large Language Models (LLMs) using LoRA or DPO. These approaches complement each other, offering flexibility for different tasks while maintaining simplicity and scalability.

## Frameworks Introduced
- **Reflexive Learning**: A nonparametric approach where agents learn from past experiences to improve performance on complex tasks.
  - When to use: Complex tasks requiring deep contextual understanding.
  - How: Agents reflect on past failures or successes, adjust their behavior accordingly, and generalize lessons.

- **Prompt Engineering with Rule-Based Systems**: Using structured prompts to guide agents through decision-making processes.
  - When to use: Situational prompting for well-defined tasks.
  - How: Crafting clear instructions and examples tailored to specific contexts.

- **LoRA Fine-Tuning**: A parametric method that fine-tunes LLMs by adjusting a small subset of parameters.
  - When to use: Fine-tuning large models for specific tasks or domains.
  - How: Applying LoRA adapters to optimize model adaptation without retraining the entire model.

- **Direct Preference Optimization (DPO)**: A technique that trains agents to prioritize preferred outputs over alternatives.
  - When to use: Tasks requiring nuanced preference learning.
  - How: Using pairwise comparisons and human evaluations to guide model optimization.

## Key Concepts
- **Nonparametric Learning**: Focuses on simple, fast, and interpretable methods for real-time tasks.
- **Fine-Tuning**: Involves adjusting model weights to specialize LLMs for specific domains or tasks.
- **Prompt Engineering**: Uses structured prompts to control agent behavior and improve task performance.
- **LoRA (Low-Rank Adaptation)**: Reduces computational overhead while maintaining model effectiveness.
- **DPO**: Employs pairwise comparisons and human evaluations to shape output quality.

## Mental Models
- **Reflexive Learning Model**: Represents an agent's ability to learn from past experiences, with key components like reflection prompts, schema merging, and iterative learning.
  - Use this when you need agents capable of handling complex tasks requiring deep contextual understanding.

- **Fine-Tuning Model**: Focuses on specializing LLMs for specific domains or tasks by adjusting a small subset of parameters.
  - Use this when you have large models but limited resources to retrain them entirely.

## Anti-patterns
- **Over-engineering**: Applying overly complex techniques to simple problems.
  - What to avoid: Spending unnecessary resources on sophisticated methods when simpler solutions exist.

- **Lack of Feedback**: Not incorporating evaluation metrics or human feedback into learning processes.
  - What to avoid: Ignoring performance improvements or regressions caused by changes in training.

- **Resource Misallocation**: Using expensive computational resources for tasks that could be handled with cheaper alternatives.
  - What to avoid: Overprioritizing resource investment without considering task requirements.

## Code Examples
```python
# Example of LoRA Fine-Tuning using Hugging Face libraries
from datasets import load_dataset
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, LoraConfig
import logging

# Load and prepare the dataset
base_model = "microsoft/Phi-3-mini-4k-instruct"
tokenizer = AutoTokenizer.from_pretrained(base_model, padding_side="right", trust_remote_code=True)
logger = logging.getLogger(__name__)

# Define LoRA configuration
lora_config = LoraConfig(
    r=8,
    lora_alpha=16,
    lora_dropout=0.05,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    bias="none",
    task_type="CAUSAL_LM"
)

# Fine-tune the model
model = AutoModelForCausalLM.from_pretrained(
    base_model,
    device_map="auto",
    torch_dtype=torch.bfloat16,
    quantization_config=BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16
    )
)

# Training arguments and DPO configuration
train_args = TrainingArguments(
    output_dir="phi3-mini-helpdesk-dpo",
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    learning_rate=5e-6,
    num_train_epochs=3,
    logging_steps=10,
    save_strategy="epoch",
    bf16=True,
    report_to=None,
    beta=0.1,
    loss_type="sigmoid",
    label_smoothing=0.0
)

dpo_args = DPOConfig(
    output_dir="phi3-mini-helpdesk-dpo",
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    learning_rate=5e-6,
    num_train_epochs=3.0,
    bf16=True,
    logging_steps=10,
    save_strategy="epoch",
    report_to=None
)

trainer = DPOTrainer(
    model=model,
    args=train_args,
    train_dataset=ds,
    ref_model=None,
    dpo_args=dpo_args
)
trainer.train()
trainer.save_model()
tok.save_pretrained(OUTPUT_DIR)
```

## Reference Tables

| Parameter | Value/Configuration |
|---|---|
| LoRA r | 8 |
| LoRA alpha | 16 |
| LoRA dropout | 0.05 |
| Target modules | ["q_proj", "k_proj", "v_proj", "o_proj"] |
| Bias | none |

## Key Takeaways
1. Start with nonparametric methods for simple tasks and gradually incorporate parametric techniques.
2. Use prompt engineering as a foundation before applying fine-tuning to ensure robust performance.
3. Apply fine-tuning selectively based on task requirements, balancing model specialization with resource constraints.
4. Regularly evaluate models using appropriate metrics and human feedback to guide learning improvements.
5. Continuously iterate and refine models based on feedback loops and evolving operational needs.

## Connects To
- Chapter 6: Reinforcement Learning
- Chapter 8: Frames of Reference
```
```