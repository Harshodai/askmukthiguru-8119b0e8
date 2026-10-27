# Chapter 4: B-Tree Basics

## Core Idea
B-Trees are essential for efficient on-disk storage management due to their high fanout and minimal balancing requirements compared to binary search trees.

## Frameworks Introduced
- **B-Tree**: A balanced tree structure optimized for disk access with high fanout (number of child nodes per parent).  
  - When to use: On-disk data structures requiring efficient insertion, deletion, and lookup operations.  
  - How: Uses node splits and merges to maintain balance while maximizing node capacity.

## Key Concepts
- **B-Tree Node**: A data structure containing up to N keys and pointers to child nodes.
- **Separator Keys**: Keys that split the tree into subtrees based on key ranges.
- **Node Splitting/Merging**: Processes for maintaining tree balance during insertions, deletions, and rebalancing.

## Mental Models
- Use B-Trees when dealing with large datasets requiring efficient disk access.  
  Think of B-Trees as optimal data structures for scenarios where minimizing pointer overhead and high fanout are critical.

## Anti-Patterns
- **Underflow during Deletions**: Occurs when sibling nodes have insufficient capacity to accommodate merged elements, leading to tree imbalance.
  - Avoid by redistributing keys or merging multiple nodes if necessary.

## Code Examples
```
<key code example>
```

## Reference Tables
| Parameter          | Description                                      |
|--------------------|---------------------------------------------------|
| Fanout (N)         | Number of child nodes per parent node.           |
| Height Calculation | Logarithm base N of total number of keys M.    |
| Lookup Complexity  | O(log N M).                                   |

## Key Takeaways
1. Use B-Trees for on-disk storage due to their efficiency in high fanout scenarios.
2. Implement splits and merges carefully to maintain balance during insertions/deletions.
3. Optimize node capacity by choosing appropriate fanout values.

## Connects To
- Indexing systems, disk-based databases, tree traversals, and balanced search trees.