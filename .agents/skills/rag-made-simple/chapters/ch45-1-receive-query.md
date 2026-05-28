# Chapter 45: 1. Receive query

## Core Idea  
The chapter introduces an adaptive retrieval architecture that classifies queries into four types (Factual, Analytical, Opinion, Contextual) and routes them to specialized strategies before using an LLM for response generation.

## Frameworks Introduced  
- **Adaptive Retrieval Architecture**:  
  - When to use: For diverse query patterns requiring different retrieval strategies.  
  - How: Classify queries into four types (Factual, Analytical, Opinion, Contextual) and route them to corresponding strategy-specific paths before LLM processing.

## Key Concepts  
- **Query Classification**: Identifying the type of query (e.g., factual, analytical).  
- **Retrieval Strategies**: Four specialized approaches for different query types.  
- **LLM-Based Classifier**: A lightweight model that routes queries to appropriate strategies with a single additional call.

## Mental Models  
- Use adaptive retrieval when queries span multiple types requiring diverse retrieval needs.  

## Anti-patterns  
- **Avoid fixed query transformations**: When queries are homogeneous, simpler approaches suffice as they may be nearly as effective and less costly.

## Code Examples  
```python
# Example of strategy-specific LLM calls for different query types
def handle_query(query):
    # Classify the query type
    if classify_query_type(query) == 'Factual':
        return apply_factual_strategy(query)
    elif classify_query_type(query) == 'Analytical':
        return apply_analytical_strategy(query)
    elif classify_query_type(query) == 'Opinion':
        return apply_opinion_strategy(query)
    else:  # Contextual
        return apply_contextual_strategy(query)

# Example of applying a strategy-specific protocol
def apply_factual_strategy(query):
    # Retrieval techniques for factual queries
    return retrieve_factual_documents(query)
```

## Reference Tables  
| Query Type | Retrieval Strategy | Key Techniques Applied |
|------------|--------------------|-----------------------|
| Factual    | Factual Retrieval  | Precision-based methods, exact matches |
| Analytical | Analytical Retrieval | Breadth-based methods, sub-query decomposition |
| Opinion    | Opinion Retrieval   | Diversity-based methods, subjective insights |
| Contextual | Contextual Retrieval| Personalization techniques, contextual relevance |

## Key Takeaways  
1. Use adaptive retrieval for systems serving diverse query types to improve response accuracy.
2. Classification adds complexity and cost but enhances retrieval quality when queries are heterogeneous.
3. Opt for simpler approaches if queries are homogeneous.

## Connects To  
- Relates to knowledge management strategies (Chapter 46).