# Chapter 38: 2. Compute distance from query to each candidate

## Core Idea
The chapter introduces a dartboard selection algorithm designed to balance relevance and diversity in information retrieval systems by iteratively selecting chunks that maximize these two objectives.

## Frameworks Introduced
- **Greedy Loop Framework**: 
  - When to use: Suitable for scenarios where redundancy is a concern, such as knowledge bases with overlapping content.
  - How: Select the most relevant chunk first, then iteratively select additional chunks that optimize a weighted combination of relevance and diversity scores.

## Key Concepts
- **Sigma (Smoothing Parameter)**: A value between 0.1 and 1 used to convert raw distances into probability-like scores via a log-normal function.
- **Dartboard Selection**: A method that prioritizes both relevance and diversity by iteratively selecting chunks with the highest combined score.

## Mental Models
- Use dartboard selection when your knowledge base contains significant redundancy, as it helps ensure each selected chunk adds unique information.
- Think of sigma as a knob to control the balance between relevance and diversity in your results.

## Anti-patterns
- **Avoid top-K retrieval**: This approach may return redundant results if the knowledge base has minimal uniqueness across its content.
- **Do not rerank after selection**: Reranking can lead to similar but irrelevant chunks being prioritized, whereas dartboard selection ensures diversity is maintained throughout the process.

## Code Examples
```python
# Example pseudocode for dartboard selection
def dartboard_selection(query, candidates):
    # Step 1: Compute distances from query to each candidate
    distances = compute_distances(query, candidates)
    
    # Step 2: Iteratively select chunks based on combined scores
    selected = []
    remaining_candidates = candidates
    
    while len(selected) < K:
        # Compute relevance and diversity scores
        relevance_scores = [compute_relevance(c) for c in remaining_candidates]
        diversity_scores = [compute_diversity(c, selected) for c in remaining_candidates]
        
        # Combine scores with weights
        combined_scores = [(relevance * alpha + diversity * beta), idx] 
        for idx, (score, relevance, diversity) in enumerate(zip(relevance_scores, relevance_scores, diversity_scores))
        
        # Select the chunk with highest score
        selected_idx = argmax(combined_scores)
        selected.append(remaining_candidates[selected_idx])
        remaining_candidates.pop(selected_idx)
    
    return selected
```

## Reference Tables

| Parameter | Value Range | Purpose |
|-----------|-------------|---------|
| Sigma (σ)  | 0.1–1       | Controls the smoothing of distance scores |

## Key Takeaways
1. Use dartboard selection when your knowledge base contains overlapping content, as it ensures each selected chunk adds unique information.
2. The algorithm balances relevance and diversity through a weighted scoring system, with weights (alpha and beta) tuning this balance based on collection characteristics.
3. Oversampling the initial candidate pool allows for a trade-off between relevance and diversity without sacrificing either significantly.

## Connects To
- Relates to fusion retrieval from Chapter 12, as dartboard selection can complement reranking techniques by ensuring diversity in results.