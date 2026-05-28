# Chapter 48: Chapter 20: Corrective RAG

## Core Idea
Corrective RAG introduces a quality gate after retrieval to evaluate document relevance, ensuring accurate and reliable answers by either using local knowledge, web search, or combining both.

## Frameworks Introduced
- **Corrective RAG**: A system that evaluates document relevance before generating answers.
  - When to use: After retrieval in any RAG pipeline where document accuracy is critical.
  - How: Incorporates a quality gate to assess each document's relevance and decide the output source.

## Key Concepts
- **Relevance Scoring**: Evaluates how well each document addresses the query, assigning scores between 0 and 1.
- **Three-Way Routing**: Based on confidence scores, directs the system to use local documents, web search, or a blend for optimal answers.

## Mental Models
- Use Corrective RAG when relying solely on local knowledge may lead to inaccurate results. Think of it as adding a filter to ensure information quality before generating responses.

## Anti-patterns
- **Blind Confidence**: Avoid using standard retrieval pipelines without evaluating document relevance, which can result in incorrect or irrelevant answers.

## Code Examples
```python
# Example of routing logic based on relevance scores
def corrective_rag_routing(relevance_scores):
    if max(relevance_scores) > 0.7:
        return "Use local document"
    elif min(relevance_scores) < 0.3:
        return "Search web"
    else:
        return "Combine local and web results"

# Demonstration of using the function
scores = [0.9, 0.5, 0.2]
result = corrective_ragRouting(scores)
print(f"Result: {result}")
```

## Reference Tables

| **Confidence Score Range** | **Action**                     |
|----------------------------|---------------------------------|
| > 0.7                      | Use local document directly    |
| < 0.3                      | Perform web search              |
| 0.3–0.7                    | Combine local and web results |

## Key Takeaways
1. Use Corrective RAG to enhance retrieval accuracy by evaluating document relevance.
2. Implement a quality gate after retrieval to decide whether to use local knowledge, web search, or both.
3. Always assess the confidence of retrieved documents before generating answers.

## Connects To
- Relates to improving retrieval systems and avoiding information gaps in technical documentation.