# Chapter 14: Chapter 5: Query Transformations: Reshaping the Question  

## Core Idea  
Query transformation is essential for improving retrieval accuracy by reshaping the original question to better match the documents' language and structure.  

## Frameworks Introduced  
- **Query Rewriting**:  
  - When to use: When the query is vague or underspecified.  
  - How: Reformulate the query to include more details, making it more precise and aligned with document language.  

- **Step-back Prompting**:  
  - When to use: When the query is too specific or narrow.  
  - How: Broaden the query to retrieve foundational context before narrowing down to detailed results.  

- **Sub-query Decomposition**:  
  - When to use: When dealing with complex, multi-faceted questions.  
  - How: Split a single question into focused sub-queries for better retrieval and integration of evidence.  

## Key Concepts  
- **Query Transformation**: The process of reshaping the query to improve retrieval accuracy.  
- **Vector Search**: A search method that relies on mathematical representations (embeddings) of text.  
- **Retrieval Accuracy**: The likelihood of finding relevant documents for a given query.  

## Mental Models  
Use query rewriting when your initial question is too broad or vague, and you need more specific terms to find precise results. Think of it as refining the camera's focus on a landscape—instead of a wide-angle view, you get a sharp, detailed shot.  

Avoid over-restrictiveness in query formulation, which can lead to missing relevant evidence due to mismatched terminology or levels of detail.  

## Anti-patterns  
- **Over-restriction**: Formulating queries that are too narrow or specific, causing the search to miss relevant but differently phrased passages.  

## Code Examples  
```python
def query_rewriting(query):
    """Reformulate a vague query into a more precise one."""
    from transformers import LlamaForCausalLM, LlamaTokenizer
    
    model = LlamaForCausalLM.from_pretrained("anthropic/llama-70b")
    tokenizer = LlamaTokenizer.from_pretrained("anthropic/llama-70b")
    
    inputs = tokenizer(query, return_tensors="np", max_length=128)
    outputs = model.generate(
        **inputs,
        do_sample=True,
        temperature=0.7,
        max_new_tokens=50
    )
    rewritten_query = tokenizer.decode(outputs[0], skip_special_tokens=True)
    
    return rewritten_query
```
**What it demonstrates**: This code uses a language model to expand and refine the original query by generating additional details, ensuring that the search is more precise.  

## Reference Tables  
| Framework | Key Points |  
|---|---|  
| Query Rewriting | Broadens queries with more details for precise retrieval |  
| Step-back Prompting | Broadens queries to retrieve foundational context before narrowing down |  
| Sub-query Decomposition | Splits complex questions into focused parts for better handling |  

## Key Takeaways  
1. Improve retrieval accuracy by transforming the original query using techniques like query rewriting, step-back prompting, and sub-query decomposition.  
2. Use query rewriting when your question is vague or broad to unpack it into more specific terms.  
3. Apply step-back prompting when dealing with overly narrow or technical questions to retrieve broader foundational context before narrowing down for detailed answers.  

## Connects To  
- Relates to Chapter 1 (Simple RAG) on understanding embeddings and vector search.