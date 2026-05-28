# Chapter 13: Proposition Chunking for Technical Books

## Core Idea
Proposition chunking transforms dense text into precise, self-contained facts that improve retrieval accuracy and context preservation.

## Frameworks Introduced
- **Proposition Chunking**: 
  - When to use: For documents requiring specific factual answers.
  - How: Decompose chunks into propositions with quality checks.

## Key Concepts
- **Proposition**: A single fact, self-contained, accurate, clear, complete, and concise.
- **Quality Gate**: Filters propositions based on accuracy, clarity, completeness, and conciseness using a second LLM model.

## Mental Models
- Use proposition chunking when precision is crucial for factual questions in dense knowledge bases.

## Anti-patterns
- Avoid standard RAG methods if context preservation is essential for broad or thematic queries.

## Code Examples
```python
# Example Proposition Generation
chunk = "The Apollo 11 mission featured Michael Collins."
propositions = [
    {"text": "Michael Collins orbited above in the command module during the Apollo 11 mission."},
    {"text": "The Apollo 11 mission was led by Michael Collins."}
]

# Quality Check Example
scored_propositions = [
    {"accuracy": 9, "clarity": 8, "completeness": 7, "conciseness": 10},
    {"accuracy": 6, "clarity": 5, "completeness": 4, "conciseness": 7}
]
filtered_propositions = [prop for prop in scored_propositions if all(score >= 7 for score in prop.values())]
```

## Reference Tables
| Parameter          | Value       |
|--------------------|-------------|
| Quality Threshold | 7/10        |

## Key Takeaways
1. Proposition chunking excels at extracting precise facts from dense text.
2. It balances context preservation with retrieval precision, ideal for specific factual questions.
3. Preparation requires multiple LLM calls but ensures high-quality output.

## Connects To
- Relates to information retrieval techniques and structured data management.

This approach streamlines technical document processing, offering efficient and accurate retrieval for users seeking specific information.