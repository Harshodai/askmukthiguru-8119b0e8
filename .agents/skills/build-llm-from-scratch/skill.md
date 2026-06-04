---
name: build-llm-from-scratch
description: "Knowledge base from 'Build a Large Language Model (From Scratch) (Sebastian Raschka) (z-library.sk, 1lib.sk, z-lib.sk).pdf'. Use when referencing concepts, patterns, or frameworks from this book."
allowed-tools:
  - Read
  - Grep
argument-hint: [topic or chapter number]
---

# Build a Large Language Model (From Scratch) (Sebastian Raschka) (z-library.sk, 1lib.sk, z-lib.sk).pdf

## How to Use This Skill
- **Without arguments** — load core frameworks for reference
- **With a topic** — ask about a specific topic; I find and read the relevant chapter
- **With chapter** — ask for `chXX`; I load that chapter file

---

## Core Frameworks & Mental Models

Here’s an alphabetical glossary of key terms from the chapters provided, along with their corresponding chapter references:

**Term** — **Definition (Ch N)**  
- **Large Language Model (LLM)**: A type of artificial intelligence that processes and generates large amounts of text data to mimic human language understanding and generation capabilities. (Ch 1)  
- **Pre-trained model**: A model trained on a large dataset without specific task-oriented supervision, designed to capture general patterns in language for downstream tasks. (Ch 2, Ch 5)  
- **Tokenization**: The process of breaking text into smaller units called tokens, which are then processed by machine learning models. (Ch 1, Ch 2)  
- **Attention mechanisms**: A component in neural networks that allows the model to focus on different parts of the input when generating or processing output. (Ch 3)  
- **GPT model**: A type of transformer-based language model developed by OpenAI for generating text in a given domain. (Ch 4, Ch 5)  
- **Classification task**: A machine learning task where the model predicts a category or label from input data. (Ch 6)  
- **Fine-tuning**: The process of adjusting a pre-trained model to perform a specific task by training it further on task-related data. (Ch 5, Ch 6, Ch 7)  
- **Unlabeled data**: Data without corresponding labels or annotations, used for unsupervised learning tasks like pre-training models. (Ch 5)  
- **Instructive fine-tuning**: A type of fine-tuning where the model is trained to follow specific instructions or perform particular tasks. (Ch 7)  
- **Transformer architecture**: A neural network architecture that uses self-attention mechanisms to process sequential data, such as text. (Ch 3, Ch 4)  
- **Context window**: The range of previous tokens a model can attend to when processing the next token in a sequence. (Ch 3)  
- **Self-attention**: A mechanism where each token in a sequence attends to other tokens to capture contextual information. (Ch 3, Ch 4)  



---

## Chapter Index

| # | Title | Key Frameworks |
|---|-------|----------------|
| [ch01](chapters/ch01-chapter-1-understanding-large-language-models.md) | Chapter 1: Understanding large language models | Key concepts and frameworks |
| [ch02](chapters/ch02-chapter-2-working-with-text-data.md) | Chapter 2: Working with text data | Key concepts and frameworks |
| [ch03](chapters/ch03-chapter-3-coding-attention-mechanisms.md) | Chapter 3: Coding attention mechanisms | Key concepts and frameworks |
| [ch04](chapters/ch04-chapter-4-implementing-a-gpt-model-from-scratch-to-generate-text.md) | Chapter 4: Implementing a GPT model from scratch to generate text | Key concepts and frameworks |
| [ch05](chapters/ch05-chapter-5-pretraining-on-unlabeled-data.md) | Chapter 5: Pretraining on unlabeled data | Key concepts and frameworks |
| [ch06](chapters/ch06-chapter-6-fine-tuning-for-classification.md) | Chapter 6: Fine-tuning for classification | Key concepts and frameworks |
| [ch07](chapters/ch07-chapter-7-fine-tuning-to-follow-instructions.md) | Chapter 7: Fine-tuning to follow instructions | Key concepts and frameworks |

## Supporting Files
- [glossary.md](glossary.md) — all key terms with definitions
- [patterns.md](patterns.md) — all techniques and design patterns
- [cheatsheet.md](cheatsheet.md) — quick reference tables and decision guides
