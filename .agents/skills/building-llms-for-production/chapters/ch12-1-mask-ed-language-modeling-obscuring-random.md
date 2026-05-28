# Chapter 12: Masked Language Modeling: Obscuring Random

## Core Idea
Masked language modeling is a cornerstone of modern large language models (LLMs), enabling them to learn context, syntax, and semantics through masked pre-training.

## Frameworks Introduced
- **BERT**: Pre-trained on masked language modeling for general NLP tasks.
  - When to use: For general text understanding and generation.
  - How: Fine-tuning BERT for specific downstream tasks like classification or summarization.
- **GPT-2**: Masked pre-training focused on text generation.
  - When to use: For tasks requiring coherent text generation, such as document completion or dialogue systems.
  - How: Pre-training GPT-2 with masked tokens to encourage diverse and context-aware outputs.
- **MaskedLM (scikit-learn)**: A simple implementation for masked pre-training.
  - When to use: For basic NLP tasks like text classification or entity recognition.
  - How: Applying masking strategies to small datasets for quick experimentation.

## Key Concepts
- **Tokenization**: Breaking text into tokens for model processing.
- **Masked Tokens**: Randomly replacing parts of input with `[MASK]` during pre-training.
- **Pre-training Objectives**: Maximizing masked cross-entropy loss or accuracy metrics like BLEU score.
- **Evaluation**: Using perplexity, precision, recall, or F1-score to assess model performance.

## Mental Models
- Use BERT when you need a general-purpose NLP model for tasks like classification or summarization.
- Think of GPT-2 as ideal for generating coherent and context-aware text outputs in tasks requiring diversity and coherence.
- MaskedLM serves as a simple starting point for experimenting with masked pre-training.

## Anti-patterns
- **Over-reliance on Masking**: Using only masked tokens without considering the model's capacity to generalize beyond training data can lead to overfitting or poor performance on unseen data.

## Code Examples
```
from transformers import BertTokenizer, BertForMaskedLM
tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')
model = BertForMaskedLM.from_pretrained('bert-base-uncased')

# Example for masked token replacement:
tokens = tokenizer.tokenize("The capital of France is [MASK].")
input_ids = tokenizer.mask(tokens, return_tensors="pt")
output = model(input_ids=input_ids)
```

This code demonstrates how to apply masking during pre-training using BERT's maskedLM implementation.

## Reference Tables
| Model       | Pre-training Objective                     | Use Case                          |
|-------------|--------------------------------------------|-------------------------------------|
| BERT        | Maximize masked cross-entropy loss          | Sentiment analysis, text classification |
| GPT-2       | Encourage diverse and context-aware outputs | Text generation, document completion |
| MaskedLM    | Simple masked pre-training                   | Basic NLP tasks                    |

## Key Takeaways
1. Use BERT for general NLP tasks requiring broad understanding.
2. Optimize GPT-2 for specialized text generation tasks.
3. Leverage maskedLM for quick experimentation on small datasets.

## Connects To
- Chapter 4: Pre-training discusses tokenization and masked pre-training in detail.
- Chapter 10: Fine-tuning covers model adaptation to specific tasks after pre-training.
- Chapter 11: Multimodal models extends the capabilities of LLMs into vision-language integration.