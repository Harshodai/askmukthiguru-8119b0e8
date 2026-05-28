# Chapter 47: 1. Receive user query

## Core Idea  
The chapter introduces explainable retrieval, a method that enhances search systems by providing clear explanations for why documents are retrieved, ensuring transparency and trust in the results.

## Frameworks Introduced  
- **Explain**: A framework that adds an explanation step after standard retrieval, pairing each document with a rationale for its relevance.  
  - When to use: Best suited for high-stakes domains requiring trust (e.g., legal, medical) or user-facing search interfaces where non-technical users interact.  
  - How: Involves crafting specific prompts to ask the language model why retrieved documents are relevant, ensuring explanations are concise and focused.

## Key Concepts  
- **Explanation Quality**: The clarity and specificity of reasons provided for document relevance, prioritizing actionable insights over generic statements.  
- **Query-awareness**: Ensuring explanations reflect the user's intent by linking retrieval decisions directly to their query.  
- **Specificity**: Providing detailed connections between the query and document content rather than broad or irrelevant comments.  
- **Brevity**: Limiting explanations to two or three sentences to maintain efficiency without sacrificing clarity.  
- **Latency Impact**: The trade-off of adding an additional language model call per retrieved document, which can increase processing time.

## Mental Models  
Use explainable retrieval when trust and transparency are critical for decision-making or user interaction. Think of it as a tool that bridges the "black box" gap in search algorithms by making retrieval logic visible.

## Anti-patterns  
- **No Explanation**: Avoid this approach when speed is more important than accuracy, such as in real-time applications where every millisecond counts.  

## Code Examples  
```python
# Example prompt for explaining relevance
query = "What are the key factors affecting cross-border transactions?"
document_content = "This document outlines the regulatory framework for cross-border transactions, including reporting thresholds and compliance requirements."

explanation_prompt = f"Identify why this document is relevant to the query about cross-border transactions. Focus on specific aspects of the document that address the query's intent."
```

What it demonstrates: How to structure a prompt to elicit specific, actionable explanations from an LLM.

## Reference Tables  
| **Aspect**         | **Explainable Retrieval**                          | **Source Attribution**                          |
|---------------------|----------------------------------------------------|--------------------------------------------------|
| Highlights          | Provides rationales for document relevance           | Highlights source spans within documents        |
| Timing              | Between retrieval and generation                 | After generation                                 |
| Focus               | On why documents were retrieved                   | On what supports the answer                    |

## Key Takeaways  
1. Explainable retrieval adds transparency by providing clear reasons for document relevance, enhancing trust in search results.  
2. Crafting explanations requires specificity, query-awareness, and brevity to be effective without overwhelming users.  
3. The trade-off of latency is justified in high-stakes applications where accuracy and accountability are prioritized.  

## Connects To  
- Relates to debugging and quality assurance techniques like the "5 Whys."  
- Connects with source attribution methods for understanding document contributions to answers.