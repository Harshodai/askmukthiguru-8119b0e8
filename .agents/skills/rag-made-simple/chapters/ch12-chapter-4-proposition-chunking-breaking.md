# Chapter 12: Proposition Chunking: Breaking

## Core Idea
Proposition chunking refines text chunks into individual propositions—smaller, precise facts—that enhance retrieval accuracy by isolating relevant information.

## Frameworks Introduced
- **Proposition Chunking**: 
  - When to use: When you need precise fact retrieval.
  - How: Split initial chunks using a language model to generate self-contained propositions.

## Key Concepts
- **Proposition**: A single, self-contained fact expressed clearly without surrounding context.
- **Character-based chunking**: Inadequate for isolating facts due to arbitrary splits and mixed content.
- **Language model**: Guides decomposition of text into propositions by applying specific rules.

## Mental Models
- Use Proposition Chunking when you need precise retrieval. It's the opposite approach compared to character-based chunking, which can cause noise and dilution.

## Anti-patterns
- **Character-based chunking**: Fails to handle boundaries well, leading to irrelevant results and mixed facts in chunks.

## Code Examples
```python
# Pseudocode for Proposition Generation
def generate_propositions(chunk):
    propositions = []
    # Split chunk into smaller parts using a language model
    # Each part becomes a proposition that expresses one fact
    # Example: "Neil Armstrong walked on the Moon..." → ["Neil Armstrong walked on the Moon in 1969", ...]
    return propositions

# Demonstration of how a chunk is split into propositions
chunk = "Graham suggests that founders should leverage their strengths rather than conform to traditional managerial practices. Founder Mode is an emerging paradigm that is not yet fully documented."
propositions = generate_propositions(chunk)
print(propositions)  # Output: ["Graham suggests...", "Founders..."]
```

This demonstrates splitting a chunk into individual propositions, each expressing one fact.

## Reference Tables

| **Chunking Method** | **Pros** | **Cons** |
|---------------------|----------|----------|
| Character-based      | Simplicity, mixed facts dilute relevance | Boundaries unclear, noise introduced |
| Proposition-based    | Precise retrieval, isolated facts | More complex setup |

## Key Takeaways
1. Understand the limitations of character-based chunking and its impact on retrieval.
2. Learn how Proposition Chunking decomposes text into individual propositions for precise fact extraction.
3. Apply Proposition Chunking to improve retrieval accuracy by isolating relevant information.

## Connects To
- Relates to Chapter 1's discussion on embedding single vectors, highlighting the need for more granular chunks.