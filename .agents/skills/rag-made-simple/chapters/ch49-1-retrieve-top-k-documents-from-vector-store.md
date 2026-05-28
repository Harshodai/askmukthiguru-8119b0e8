# Chapter 49: Corrective RAG  
## Core Idea  
Corrective RAG improves upon standard Retrieval-Augmented Generation (RAG) by evaluating retrieved documents for relevance before generating responses. This ensures higher accuracy, especially when local knowledge bases have gaps or incomplete coverage.

## Frameworks Introduced  
- **Corrective RAG**:  
  - When to use: When relying solely on vector store retrieval may lead to inaccurate results due to uneven knowledge base coverage.  
  - How: Incorporates relevance evaluation steps between retrieval and generation, including fallback strategies for web searches when local documents are insufficient.

## Key Concepts  
- **Corrective RAG**: A framework that evaluates retrieved documents' relevance before generating responses, ensuring higher accuracy in cases of incomplete knowledge bases.  
- **Relevance Score Thresholding**: A method to filter out low-confidence retrieval results based on predefined score thresholds (e.g., >0.7 for confident retrieval).  
- **Web Search Integration**: Incorporates fallback strategies when local documents are insufficient, including query rewriting and knowledge refinement.  
- **Knowledge Refinement**: A process that extracts key points from web search results to enhance the quality of retrieved information.

## Mental Models  
Use Corrective RAG when:  
- Your knowledge base has uneven coverage or gaps in certain topics.  
- You need to handle queries that fall outside the scope of indexed documents.  
- Accuracy is more critical than speed, and occasional delays due to incomplete results are acceptable.

Think of Corrective RAG as a safety net for standard RAG by adding an explicit relevance evaluation step between retrieval and generation.

## Anti-patterns  
- **Standard RAG**: Avoid using this when your knowledge base has gaps or incomplete coverage because it lacks the additional evaluation steps that ensure higher accuracy in such cases.

## Code Examples  
```python
def corrective_rag(query, vector_store, k=3):
    # Step 1: Retrieve top-K documents
    docs = vector_store.retrieve(query, k=k)
    
    # Step 2: Score each document for relevance
    scores = vector_store.score(query, docs)
    
    # Step 3: Find maximum relevance score
    max_score = max(scores.values())
    
    # Step 4: Evaluate confidence and select sources
    if max_score > 0.7:
        selected_doc = list(docs.keys())[scores.idxmax()]
    elif max_score < 0.3:
        rewritten_query, web_results = refine_query(query)
        selected_doc = combine_local_and_web(rewritten_query, web_results)
    else:
        selected_doc = combine_local_and_web(docs, scores)
        
    # Step 5: Generate response from the selected source
    response = generate_response(selected_doc)
    
    return response
```

## Reference Tables  
| Comparison Metric          | Standard RAG                                                                 | Corrective RAG                                                                 |
|----------------------------|-----------------------------------------------------------------------------|------------------------------------------------------------------------------|
| Latency                     | Low Latency                                                                | Higher Latency (due to evaluation steps and potential web searches)        |
| Complexity                 | Low Complexity                                                             | Medium Complexity (includes relevance scoring, query rewriting, and web search integration) |
| Cost                       | Low Cost                                                                  | Potentially Higher Cost (due to multiple API calls and web search infrastructure) |
| Accuracy Benefit           | None                         | Significant Improvement in accuracy when local knowledge is incomplete or gaps exist |

## Key Takeaways  
1. Corrective RAG ensures higher accuracy by evaluating retrieved documents for relevance before generating responses.  
2. Use fallback strategies like web searches when local documents are insufficient to cover the query.  
3. Balance between speed and accuracy by dynamically selecting sources based on confidence levels.

## Connects To  
- Relates to Explainable Retrieval (Chapter 19) in addressing transparency vs. accuracy trade-offs, but Corrective RAG focuses on improving accuracy through dynamic source selection rather than explaining retrieval decisions.