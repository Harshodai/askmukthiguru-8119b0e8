# Chapter 4: Storage and Retrieval

## Core Idea
This chapter teaches you how databases store and retrieve data efficiently by understanding different storage mechanisms, their trade-offs, and when to use each approach.

## Frameworks Introduced
- **B-tree based indexes**: 
  - When to use: Relational databases with range queries and moderate write volumes.
  - How: Build a balanced tree structure for fast lookups, splits, and merges. Ideal for sequential scans but less efficient for heavy writes or complex queries.

- **LSM-trees (Log-Structured Merge Trees)**:
  - When to use: High-write environments like web servers or NoSQL databases.
  - How: Use append-only logs for initial writes, then merge segments incrementally into SSTables. Suitable for large-scale data with predictable patterns.

## Key Concepts
- **B-tree**: A balanced tree structure that allows fast key-value lookups by maintaining sorted keys and child nodes in a hierarchical manner.
- **LSM-tree**: Combines multiple SSTables into larger segments to optimize range queries, even as data grows.
- **SSTable (Sort-Sequence Table)**: Stores sorted key-value pairs across multiple file-based segments for efficient range queries.
- **B+ tree**: Similar to a B-tree but stores all values in leaves, improving disk I/O efficiency by reducing the need for frequent node splits.

## Mental Models
- Use B-trees when you need fast sequential access and moderate write volumes.
- Use LSM-trees when you have high write pressure and can tolerate periodic compaction.
- Think of indexes as data containers that enable efficient retrieval but require careful management to avoid performance bottlenecks.

## Anti-patterns
- Overusing B-trees in relational databases: They are not optimal for complex queries or high-write scenarios.
- Neglecting indexing altogether: This leads to poor performance and scalability issues.

## Code Examples
```python
from typing import List, Tuple

class IndexNode:
    def __init__(self, left: int = 0, right: int = float('inf'), size: int = 1):
        self.left = left
        self.right = right
        self.size = size
        self.children = []

def build_b_tree(keys: List[T], values: List[V]) -> IndexNode:
    nodes = []
    for key, value in zip(keys, values):
        node = IndexNode()
        node.key = key
        node.value = value
        nodes.append(node)
    
    def split_child(node: IndexNode) -> Tuple[IndexNode, IndexNode]:
        if node.size == 1:
            return (node, None)
        
        mid = (node.left + node.right) // 2
        child = next(n for n in reversed(nodes) if n.left <= mid and n.right >= mid)
        new_child = IndexNode(child.left, child.right, size=child.size - 1)
        new_child.children.append(child)
        return (child, new_child)
    
    root = nodes[0]
    for node in nodes[1:]:
        left, right = split_child(node)
        if left:
            left.children.append(left)
        else:
            left = None
        if right:
            right.children.append(right)
        else:
            right = None
    
    return root
```

## Reference Tables

| Storage Mechanism      | Use Case                          | Performance Trade-offs                     |
|------------------------|------------------------------------|--------------------------------------------|
| B-trees                | Relational databases, moderate writes  | Fast lookups, slower compaction             |
| LSM-trees              | High-write environments, web apps     | Efficient for range queries, higher memory usage |

## Key Takeaways
1. Choose the right storage mechanism based on your workload: Use B-trees for moderate writes and LSM-trees for high write volumes.
2. Maintain indexes efficiently to avoid performance degradation.
3. Understand trade-offs between different structures to make informed decisions.

## Connects To
- Relational databases, NoSQL databases, caching systems