# Chapter 5: Encoding and Evolution

## Core Idea
The choice of encoding format is critical for ensuring backward compatibility as services evolve or migrate together.

## Frameworks Introduced
- **JSON Schema**: A lightweight data interchange format that extends JSON with schemas, used for defining data formats.  
  - When to use: Define consistent data formats across systems.
  - How: Use predefined schemas and optional extensions to maintain flexibility.
- **Avro**: A high-performance serialization/deserialization format designed for fast interoperation.  
  - When to use: Build scalable distributed systems requiring high performance and extensibility.
  - How: Encode/decode data using schemas, supporting forward/backward compatibility with evolving formats.
- **Protocol Buffers**: A binary encoding optimized for speed and network efficiency.  
  - When to use: Optimize data transmission in large-scale distributed systems.
  - How: Encode/decode data in native byte format with optional schema support.

## Key Concepts
- **Protocol Buffer**: Encodes fields as varints, using fixed-length integers for small values and variable-length integers for larger ones.  
- **JSON**: A text-based encoding suitable for client-server applications but less efficient for large-scale data flows.  
- **Avro**: Combines the simplicity of JSON with the performance of Protocol Buffers, supporting both binary and text formats.

## Mental Models
- Use Avro when you need a balance between schema flexibility and high-performance data transmission.
- Use JSON Schema when you require precise control over data formats in distributed systems.
- Avoid non-protocol-compliant encodings without considering their impact on future-proofing.

## Anti-patterns
- **Using non-Protocol Buffers for text-heavy data**: Leads to bloated logs and inefficient serialization.  
  - Why it fails: Inefficient encoding for text data, making log storage and retrieval slow.
- **Ignoring schema evolution in Avro**: Results in broken systems when formats change unexpectedly.

## Code Examples
```python
from avro.data import recordtypes
from avro.schmas import Schema

# Example of using Avro schemas
schema = recordtypes.Registry()
recordtypes.add_int64("int64")
recordtypes.add_string("string")

# Encode a record with optional fields
fields = {"int64": 123, "string": "hello"}
encoded_data, _ = schema.encode(fields)

# Decode the encoded data while respecting schemas
decoded_data = schema.decode(encoded_data)
```

## Reference Tables
| Framework      | Encoding/Decoding Mechanism                     |
|---------------|----------------------------------------------------|
| JSON         | Text-based with limited performance for large data |
| Protocol Buffers| Binary format optimized for speed and network efficiency |
| Avro          | Combines simplicity of JSON with high-performance serialization |

## Key Takeaways
1. Choose the right encoding based on your system's requirements, such as performance or schema flexibility.
2. Use schemas to maintain backward compatibility when data formats evolve.
3. Optimize for future-proofing by selecting encodings that support easy migration between versions.

## Connects To
- Data flow in databases (Chapter 4)
- Event-driven architectures (Section on Temporal)