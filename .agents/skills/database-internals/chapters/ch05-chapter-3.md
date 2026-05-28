# Chapter 5: File Formats

## Core Idea
The chapter teaches how to organize data on disk efficiently using binary formats that support fast access while managing memory effectively.

## Frameworks Introduced
- **Slotted Page Layout**: Uses fixed-size header, cells, and pointers.  
  - When to use: For variable-size records requiring minimal overhead.
  - How: Cells are organized into pages with headers for offsets; keys are sorted alphabetically but stored in insertion order.

## Key Concepts
- **Primitive Types**: Basic data types (integers, strings) represented as fixed-size bytes.
- **Serialization**: Converting binary data to a sequence of bytes using encoding schemes like UTF-8 or varints.
- **Variable-Sized Records**: Data records with non-fixed sizes stored in cells that can grow/shrink based on content.
- **Slotted Pages**: Page structures with headers, cell pointers, and variable-size cells.

## Mental Models
- Use slotted pages when you need to handle variable-size data efficiently.
- Think of B-Trees as a page-based structure where each node fits into a single page.

## Anti-Patterns
- Avoid fragmented pages leading to wasted space or inefficient layouts.  
  - What fails: Over-reliance on fixed-size cells causing fragmentation and inefficiency.

## Code Examples
```python
# Example of cell layout in slotted pages
class Cell:
    def __init__(self, page_id):
        self.page_id = page_id
        
    @classmethod
    def from_bytes(cls, bytes, offset=0):
        cls_size = 4
        key_size = (bytes[offset:offset+cls_size]).decode('utf-8')
        value_size = int.from_bytes(bytes[offset+cls_size:offset+cls_size+4], byteorder='big')
        data = bytes[offset+cls_size+4 : offset + cls_size + 4 + value_size]
        return cls(page_id, key_size, value_size, data)
```

## Reference Tables
| Parameter       | Data Type          | Description                          |
|-----------------|--------------------|---------------------------------------|
| Page Size        | Fixed              | Typically 4-16 KB for B-Trees           |
| Header Length   | Variable          | Contains metadata about cells         |

## Key Takeaways
1. Use slotted pages to efficiently store variable-size records with minimal overhead.
2. Implement B-Trees as page-based structures for fast access and memory management.
3. Always manage page space to avoid fragmentation and improve performance.

## Connects To
- Chapter 4 on B-Trees: Discusses on-disk storage techniques used in B-Trees.
- Chapter 6 on Memory Management: Explores external memory handling strategies.