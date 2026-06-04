---
name: llms-in-production
description: "Knowledge base from 'LLMs in Production From language models to successful products (Christopher Brousseau, Matthew Sharp) (z-library.sk, 1lib.sk, z-lib.sk).pdf'. Use when referencing concepts, patterns, or frameworks from this book."
allowed-tools:
  - Read
  - Grep
argument-hint: [topic or chapter number]
---

# LLMs in Production From language models to successful products (Christopher Brousseau, Matthew Sharp) (z-library.sk, 1lib.sk, z-lib.sk).pdf

## How to Use This Skill
- **Without arguments** — load core frameworks for reference
- **With a topic** — ask about a specific topic; I find and read the relevant chapter
- **With chapter** — ask for `chXX`; I load that chapter file

---

## Core Frameworks & Mental Models

Here is an organized glossary based on the provided chapters:

- **AI** — Artificial Intelligence, a branch of computer science focused on creating systems that can perform tasks requiring human intelligence. (Ch12)
  
- **LLM** — Large Language Model, a type of AI system that understands and generates human language. (Ch1)

- **Tokens** — The basic units in Natural Language Processing (NLP) used to represent words or subwords in models like BERT or GPT. (Ch2)

- **Context Window Size** — The amount of context a model can consider when processing text, crucial for tasks requiring understanding of surrounding information. (Ch2)

- **Pre-trained Models** — Models like BERT and GPT that have been trained on large datasets to perform various NLP tasks before being fine-tuned for specific applications. (Ch2)

- **API** — Application Programming Interface, a set of protocols, tools, and definitions used to interact with a software application. (Ch3)
  
- **Rate Limits** — Restrictions in place to prevent abuse or overuse of an API by limiting the number of requests from a single source. (Ch3)

- **RESTful APIs** — A set of protocols that define how resources can be accessed, updated, and deleted using HTTP methods like GET, POST, PUT, etc. (Ch3)

- **Training Data** — The dataset used to train an LLM, where the model learns patterns from this data. (Ch5)

- **Annotation** — The process of labeling or marking up data to provide signals for training models, such as in sentiment analysis. (Ch4)

- **Data Pipelines** — Systems that collect, process, and prepare raw data into a format suitable for training machine learning models. (Ch4)

- **Fine-tuning** — The process of adjusting pre-trained models to improve their performance on specific tasks or datasets. (Ch5; Ch7)

- **Overfitting** — A situation where a model performs well on training data but poorly on new, unseen data due to excessive complexity. (Ch5)

- **Tokenization** — The division of text into tokens to facilita

---

## Chapter Index

| # | Title | Key Frameworks |
|---|-------|----------------|
| [ch01](chapters/ch01-chapter-1-words-awakening-why-large-language-models-have-captured-attention.md) | Chapter 1: Words' awakening: Why large language models have captured attention | Key concepts and frameworks |
| [ch02](chapters/ch02-chapter-2-large-language-models-a-deep-dive-into-language-modeling.md) | Chapter 2: Large language models: A deep dive into language modeling | Key concepts and frameworks |
| [ch03](chapters/ch03-chapter-3-large-language-model-operations-building-a-platform.md) | Chapter 3: Large language model operations: Building a platform | Key concepts and frameworks |
| [ch04](chapters/ch04-chapter-4-data-engineering-for-large-language-models-setting-up.md) | Chapter 4: Data engineering for large language models: Setting up | Key concepts and frameworks |
| [ch05](chapters/ch05-chapter-5-training-large-language-models-how-to-generate.md) | Chapter 5: Training large language models: How to generate | Key concepts and frameworks |
| [ch06](chapters/ch06-chapter-6-large-language-model-services-a-practical-guide.md) | Chapter 6: Large language model services: A practical guide | Key concepts and frameworks |
| [ch07](chapters/ch07-chapter-7-prompt-engineering-becoming-an-llm-whisperer.md) | Chapter 7: Prompt engineering: Becoming an LLM whisperer | Key concepts and frameworks |
| [ch08](chapters/ch08-chapter-8-large-language-model-applications-building.md) | Chapter 8: Large language model applications: Building | Key concepts and frameworks |
| [ch09](chapters/ch09-chapter-9-creating-an-llm-project-reimplementing-llama-3.md) | Chapter 9: Creating an LLM project: Reimplementing Llama 3 | Key concepts and frameworks |
| [ch10](chapters/ch10-chapter-10-creating-a-coding-copilot-project.md) | Chapter 10: Creating a coding copilot project | Key concepts and frameworks |
| [ch11](chapters/ch11-chapter-11-deploying-an-llm-on-a-raspberry-pi-how-low-can-you-go.md) | Chapter 11: Deploying an LLM on a Raspberry Pi: How low can you go? | Key concepts and frameworks |
| [ch12](chapters/ch12-chapter-12-production-an-ever-changing-landscape.md) | Chapter 12: Production, an ever-changing landscape | Key concepts and frameworks |

## Supporting Files
- [glossary.md](glossary.md) — all key terms with definitions
- [patterns.md](patterns.md) — all techniques and design patterns
- [cheatsheet.md](cheatsheet.md) — quick reference tables and decision guides
