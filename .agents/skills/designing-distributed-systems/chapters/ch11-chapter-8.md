# Chapter 12: Chapter 8

## Core Idea
The Scatter/Gather pattern enhances request responsiveness by distributing computation across multiple nodes, reducing latency through parallel processing.

## Frameworks Introduced
- **Scatter/Gather Pattern**: 
  - When to use: Efficiently handle many simultaneous requests requiring independent computations.
  - How: Distribute tasks across a tree structure with a root and leaves; each leaf processes a portion of the task in parallel.

## Key Concepts
- **Scatter/Gather Pattern**: A distributed system where computation is split across multiple nodes for parallel processing.
- **Replicated System**: Each node has its own copy of data, ensuring reliability but with increased storage requirements.
- **Sharded System**: Data is partitioned across multiple nodes to handle large datasets efficiently.

## Mental Models
- Use Scatter/Gather when you need to break down tasks into independent subtasks that can be processed in parallel. Think of it as distributing computation rather than data.

## Anti-patterns
- **Not Using Scatter/Gather**: Avoid if the task cannot be broken into independent subtasks or if increased overhead outweigh benefits without sufficient scaling advantages.

## Code Examples
```python
# Example code for document search using Scatter/Gather pattern

def document_search(request):
    # Split request into terms
    terms = request.split()
    
    # Distribute terms to leaf nodes
    leaves = distribute_terms(terms)
    
    # Process each term on respective leaves
    responses = []
    for leaf, term in zip(leaves, terms):
        response = leaf.process(term)
        responses.append(response)
    
    # Combine responses from all leaves
    combined_response = combine_responses(responses)
    
    return combined_response
```

- **What it demonstrates**: Distributes independent subtasks (processing each term) across multiple nodes and combines results.

## Reference Tables

| Parameter          | Description                                      |
|--------------------|--------------------------------------------------|
| **Leaf Distribution** | Determines how tasks are split among leaf nodes. |
| **Root Distribution** | Manages task allocation from the root to leaves.  |

## Key Takeaways
1. Use Scatter/Gather when you need to handle many simultaneous requests with independent computations.
2. Replication and sharding can enhance scalability but introduce overhead and reliability considerations.
3. Be mindful of the straggler problem, which can significantly impact performance.

## Connects To
- Relates to distributed systems concepts like replication (Chapter 7) and sharding (Chapter 9).