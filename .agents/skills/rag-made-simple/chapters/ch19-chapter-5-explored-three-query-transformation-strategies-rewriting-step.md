# Chapter 20: HyDE: Bridging the Gap Between Queries and Documents  

## Core Idea  
HyDE generates a hypothetical document from the query to improve retrieval in scenarios where questions and documents don't align structurally.  

## Frameworks Introduced  
- **HyDE**: Transforms the question into an answer-shaped document for search, bridging "document space" gaps.  
  - When to use: When retrieval underperforms due to structural mismatch between queries and documents.  
  - How: Generates a hypothetical document from the query and uses its embedding for search.  

## Key Concepts  
- **Document Space**: Documents are compared directly with each other, unlike "question space" where questions are compared to documents.  
- **Structural Mismatch**: The gap between query structure and document structure that HyDE addresses.  

## Mental Models  
- Use HyDE when the question is clear but retrieval underperforms due to structural mismatch.  
- Think of HyDE as a method that generates a plausible answer shape for search, even if it's not factually correct.  

## Anti-patterns  
- **Avoid query transformations**: When the question itself is sufficient and transformation adds unnecessary complexity or latency.  

## Code Examples  
```python
def generate_hyde_document(query):
    """Transforms the query into a hypothetical document."""
    response = model.generate(
        prompt=f"Imagine you are an expert in this domain. Create a detailed paragraph explaining {query}.",
        temperature=0.3,
        max_tokens=1000
    )
    return response.choices[0].text

# Demonstration:
# query = "What caused the Great Depression?"
# hypothetical_doc = generate_hyde_document(query)
```

## Reference Tables  
| Factor       | Impact on Retrieval | Technique Comparison |
|--------------|---------------------|-----------------------|
| Latency      | High                | Lower than transformations |
| Complexity   | Low                 | No changes to storage |
| Cost         | Medium              | One additional LLM call per query |

## Key Takeaways  
1. Use HyDE when the question is clear but retrieval underperforms due to structural mismatch.  
2. HyDE complements query transformations by reshaping questions into answer-shaped documents.  
3. Optimize for domain knowledge in language models to enhance retrieval quality.  

## Connects To  
- Chapters on information retrieval and query processing techniques.