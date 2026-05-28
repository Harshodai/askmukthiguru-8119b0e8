# Chapter 37: Dartboard Retrieval

## Core Idea
Dartboard Retrieval balances relevance and diversity in search results to provide comprehensive answers, avoiding redundancy and ensuring each result adds unique value.

## Frameworks Introduced
- **Dartboard Retrieval**: A method that selects diverse yet relevant results by iteratively evaluating candidates based on both similarity to the query and novelty compared to previously selected results.
  - When to use: When search results are expected to contain redundant information, such as in technical knowledge bases.
  - How: Retrieve an oversampled pool of candidates, then iteratively select each result by balancing relevance and diversity.

## Key Concepts
- **Diversity**: Results that cover different aspects or topics related to the query.
- **Relevance**: How closely a result matches the query's intent.
- **Oversampling**: Retrieving more candidate results than needed to allow selection of diverse ones.

## Mental Models
- Use Dartboard Retrieval when you need search results that are both relevant and varied, ensuring no single source dominates the output.

## Anti-patterns
- **Pure Similarity Ranking**: This approach leads to redundant results, creating an echo chamber effect by favoring similar but non-diverse information.

## Code Examples
```python
# Example pseudocode for Dartboard Retrieval algorithm

def dartboard_retrieval(query, K=5, oversampling_factor=3):
    # Step 1: Retrieve a larger candidate pool
    candidates = retrieve_candidates(query, size=K * oversampling_factor)
    
    # Step 2: Iteratively select top-K results with balance of relevance and diversity
    selected = []
    remaining_candidates = candidates.copy()
    
    for i in range(K):
        if i == 0:
            # First selection based solely on relevance
            selected.append(max(remaining_candidates, key=lambda x: similarity(x, query)))
            remaining_candidates.remove(selected[-1])
        else:
            # Calculate scores combining relevance and diversity
            scores = {}
            for candidate in remaining_candidates:
                diversity_score = max([distance(candidate, selected_chunk) for selected_chunk in selected])
                score = (relevance_score * weight_relevance) + (diversity_score * weight_diversity)
                scores[candidate] = score
            
            # Select the highest scoring candidate
            selected.append(max(scores.values(), key=lambda x: next(iter(x))))
            remaining_candidates.remove(selected[-1])
    
    return selected

# Example of a similarity calculation function
def similarity(candidate, query):
    return cosine_similarity(embeddings[candidate], embeddings[query])

# Example of distance calculation for diversity
def distance(candidate, selected_chunk):
    return 1 - cosine_similarity(embeddings[candidate], embeddings[selected_chunk])
```

## Reference Tables

| Parameter        | Value/Description                     |
|------------------|---------------------------------------|
| K                | Number of final results to select (default=5) |
| Oversampling Factor | Multiplier for initial candidate pool size (default=3x) |
| Weight Relevance  | Configurable parameter balancing relevance (0-1) |
| Weight Diversity  | Configurable parameter balancing diversity    (0-1) |

## Key Takeaways
1. Use Dartboard Retrieval to balance relevance and diversity in search results.
2. Retrieve an oversampled pool of candidates to allow selection of diverse ones.
3. Iteratively select each result by balancing relevance and novelty compared to previously chosen results.

## Connects To
- Relates to information retrieval systems aiming to provide comprehensive yet non-redundant answers.
- Connects with techniques in technical knowledge management, such as semantic search and topic modeling.