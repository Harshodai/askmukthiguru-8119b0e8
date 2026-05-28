# Chapter 9: B-Tree Variants

## Core Idea
B-Tree variants provide optimized alternatives to traditional B-Trees for different storage environments, addressing limitations in write performance, space overhead, and concurrency control.

## Frameworks Introduced
1. **Copy-on-WRITE B-Tree**: Lazy evaluation with buffering at the node level or group nodes.
   - When to use: Spinning disks where batched writes are feasible.
   - How: Writers buffer changes in memory; readers synchronize before accessing disk.
2. **Lazy B-Trees**: Buffering at the node level or grouping nodes for updates.
   - When to use: SSDs with multiple I/O operations possible.
   - How: Batches writes into a small buffer; deletes mark records as gone without removing them from disk until necessary.
3. **FD-Trees (Immutable Sorted Runs)**: Fixed-size run pages and immutable sorted runs on disk.
   - When to use: Reduces disk space overhead in environments with frequent updates.
   - How: Updates buffered in the backing store; structural changes handled lazily.
4. **Bw-Trees**: In-memory data structures for buffering, compare-and-swap operations, and virtual pointers between logical nodes.
   - When to use: Environments requiring cache-friendly access patterns without latches.
   - How: Efficient lazy updates reduce I/O overhead while maintaining high performance.

## Key Concepts
- **Copy-on-WRITE B-Tree**: Uses immutable node structures on disk with buffering for writer synchronization.
- **Lazy B-Trees**: Employs buffering to handle updates in memory and deferred deletes.
- **FD-Trees**: Utilizes fixed-size run pages and immutable sorted runs to minimize space overhead.
- **Bw-Trees**: Combines in-memory buffers with compare-and-swap operations for efficient lazy updates.

## Mental Models
- Use Copy-on-WRITE B-Tree when batched writes are feasible (e.g., spinning disks).
- Think of Lazy B-Trees as an optimized version of Copy-on-WRITE, suitable for SSDs.
- Apply FD-Trees in environments where disk space overhead is a concern.
- Utilize Bw-Trees for cache-friendly access patterns and low concurrency.

## Anti-patterns
1. **High Write Amplification**: In environments without batched writes (e.g., spinning disks).
2. **Inefficient I/O Operations**: Lack of batching in node-level or group-based buffering approaches.
3. **High Space Overhead**: Fixed-size run pages requiring extra storage upfront for updates.

## Code Examples
```python
# Example Pseudocode for Lazy B-Tree Buffering
class LazyBTreeNode:
    def __init__(self, key):
        self.key = key
        self.left = None
        self.right = None
        self.parent = None

def update_node(node, value):
    # Buffer pending updates in memory
    pass  # Implemented by buffering mechanism
```

## Reference Tables
| **B-Tree Variant**      | **Key Characteristics**                                                                 |
|-------------------------|---------------------------------------------------------------------------------------|
| Copy-on-WRITE B-Tree   | Lazy evaluation with node-level or group-node buffering; high write amplification avoided. |
| Lazy B-Trees            | Batches updates into a small buffer; deferred deletes until necessary.                   |
| FD-Trees                | Fixed-size run pages and immutable sorted runs to reduce disk space overhead.          |
| Bw-Trees                | In-memory buffers for deferred writes, compare-and-swap operations, virtual pointers.    |

## Key Takeaways
1. Use Copy-on-WRITE B-Tree when batched writes are feasible.
2. Optimize with Lazy B-Trees in SSD environments where I/O operations can be batched.
3. Apply FD-Trees to reduce disk space overhead in update-intensive scenarios.
4. Leverage Bw-Trees for cache-friendly access patterns and low concurrency.

## Connects To
- Copy-on-Write (Chapter 6)
- Lazy Evaluation (Chapter 7)
- SSD Optimization Techniques