```markdown
# Chapter 5: Encoding and Evolution

## Core Idea
The chapter discusses how systems must handle data evolution while maintaining compatibility between old and new code versions. It emphasizes the importance of encoding formats, schema evolution strategies, and ensuring backward and forward compatibility.

## Frameworks Introduced
- **JSON Schema**: A flexible format for defining data schemas with JSON-like syntax.
  - When to use: Define complex data structures with validation rules.
  - How: Specifies field names, types, and optional metadata.
  - Anti-pattern: Overcomplicating schemas without clear purpose.

- **Protocol Buffers**: Binary encoding optimized for speed and space.
  - When to use: Encode large datasets efficiently in distributed systems.
  - How: Uses variable-length integers and tags for fields.
  - Anti-pattern: Adding new fields without updating schema versions.

- **Avro**: Compact binary encoding with a lightweight schema language.
  - When to use: Encode data for high-performance systems requiring minimal overhead.
  - How: Uses schemas that match exactly between writer and reader.
  - Anti-pattern: Mismatched schemas causing decoding errors.

## Key Concepts
- **Schema Evolution**: Process of updating data formats while maintaining compatibility.
- **Backward Compatibility**: Ensuring old code can read new data without changes.
- **Forward Compatibility**: Allowing new code to read old data without issues.
- **Encoding vs. Serialization**: Differentiate between encoding (data transformation) and serialization (serialization for transport).

## Mental Models
- Use JSON Schema when you need precise control over data structures with validation.
- Choose Protocol Buffers for high-performance, large-scale systems.
- Opt for Avro for compact binary formats in modern applications.

## Anti-patterns
- Avoid using JSON Schema without clear requirements to prevent complexity and ambiguity.
- Do not use Protocol Buffers for small datasets where simpler formats suffice.
- Refrain from adding fields with default values that break backward compatibility.

## Code Examples
```python
# Example of JSON Schema
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "patternProperties": {
    "userName": {
      "type": "string",
      "pattern": "^([^\\s]+)$"
    }
  },
  "additionalProperties": false
}
```

## Reference Tables

| Framework       | Encoding Type          | Use Case                          |
|----------------|------------------------|------------------------------------|
| JSON           | Textual               | Simple, human-readable data       |
| Protocol Buffers| Binary              | High-performance, large datasets   |
| Avro           | Binary              | Compact, modern systems            |

## Key Takeaways
1. Choose the right encoding format based on performance needs and data size.
2. Use JSON Schema for complex schemas with validation requirements.
3. Optimize for space and speed with Protocol Buffers or Avro.

## Connects To
- Chapter 4: Evolvability in systems design
```