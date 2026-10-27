# Chapter 9: Chapter 3: Reliable RAG: Building Trust Through Verification

## Core Idea
Reliable RAG introduces quality control layers after retrieval and before generation to filter out irrelevant information and ensure accurate answers.

## Frameworks Introduced
- **Inspection Station Metaphor**: Similarto a factory assembly line with checkpoints for quality control.
  - When to use: To ensure high-quality data flows through the system.
  - How: By adding inspection points between retrieval and generation stages.

## Key Concepts
- **Candidate Documents**: The set of documents retrieved by RAG, typically four or more.
- **Relevance Grading**: Filtering step that assesses if a chunk is relevant to the user's query.
- **Fact-Checking**: Verifying the accuracy of generated answers against the source material.
- **Traceability**: Ensuring every claim can be traced back to its source for accountability.

## Mental Models
Use inspection stations when building RAG systems to ensure data quality. Think of it as a bouncer filtering irrelevant information before it reaches the generation stage.

## Anti-patterns
- **Noise in Retrieval**: Retrieving irrelevant chunks that pass similarity checks.
  - Fails because it distracts or misleads the system.
- **Unsupported Claims Without Context**: Generated answers with fabricated information.
  - Fails because users gain false confidence in incorrect information.

## Code Examples
```markdown
Algorithm Sketch: Relevancy Grading  
1. Examine each chunk for keyword overlap or semantic connection to the user's question.
2. Grade the chunk as relevant if it meets basic criteria (even partial matches pass).
3. Allow lenient grading to filter out obvious noise efficiently.
```

## Reference Tables

| Parameter          | Value/Decision |
|--------------------|----------------|
| Typical Candidate Documents | 4              |
| Grading Leniency Level | Low            |

## Key Takeaways
1. Add verification steps between retrieval and generation to ensure quality data flows through the system.
2. Use relevance grading to filter out irrelevant chunks before they reach the generation stage.
3. Implement traceability to hold every claim accountable for its source.

## Connects To
- Relates to chapters on RAG basics (Chapter 1) and fact-checking (later chapters).