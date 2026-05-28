# Chapter 10: Stream Processing

## Core Idea
Stream processing is a powerful approach to handle real-time data ingestion, event processing, and complex query execution by analyzing data as it flows through a system.

## Frameworks Introduced
- **Apache Flink**: A high-throughput stream processing framework designed for handling large-scale, real-time data streams. It supports batch operations, event sourcing, and fault tolerance.
  - When to use: Ideal for scenarios requiring high throughput, low latency, and fault-tolerant stream processing.
  - How: Utilizes Flink's built-in APIs like `stream()`, `write()`, and `execute()` to process data in-memory buffers. Supports both batch and event-based processing.

- **Kafka**: A distributed streaming platform for building real-time applications with low latency, fault tolerance, and scalability. It is often used as a messaging layer for stream processing systems.
  - When to use: Suitable for building scalable, fault-tolerant message queues or integrating stream data into existing systems.
  - How: Uses Kafka topics as event streams and consumes messages through consumers like Apache Flink.

- **H2**: A real-time database system optimized for streaming applications. It provides fast reads and writes with low latency and supports batch processing for near-zero-latency analytics.
  - When to use: Best for systems requiring low-latency, high-throughput data storage and retrieval.
  - How: Uses H2's in-memory buffers and real-time iterators to process events in constant time.

- **Apache Samza**: A stream processing framework built on top of Apache Kafka. It provides batch processing capabilities while maintaining the same interface as Flink.
  - When to use: Ideal for systems requiring batch processing alongside streaming data while maintaining compatibility with existing infrastructure.
  - How: Leverages Samza's batch engine and event sourcing features to handle complex queries efficiently.

## Mental Models
- **Event Sourcing**: A causality model that captures the order of events in a distributed system by writing writes-within-writes. It ensures data consistency across multiple sources even with partial or delayed updates.
  - Use X when dealing with systems requiring causality and event ordering, such as real-time analytics or transactional systems.

## Anti-patterns
- **No Global Clock**: Avoid using a single global clock for time-sensitive applications to prevent synchronization issues. Instead, use local clocks and handle time differences explicitly.
  - What to avoid: Relying on a shared notion of time without considering the physical locations and their varying clock offsets.

- **Non-Causality**: Do not assume causality in systems where events are independent or asynchronous. This can lead to incorrect event ordering and missing dependencies between data points.
  - What to avoid: Making assumptions about event order when there is no inherent temporal relationship between them, such as in non-deterministic distributed systems.

## Code Examples
```
key code example
```
from flink import Stream

# Example stream processing using Flink
stream = Stream()
stream("user_activity", columns=["timestamp", "name", "status"])
    .write("log") // Write to log table
    .execute(lambda p: p[0].strftime('%Y-%m-%d %H:%M:%S') + ' - ' +
               f"'{p[1]} activity of {p[2]}")
```
- **What it demonstrates**: This example shows how to create a stream, write data to a log table, and execute custom processing logic on each event.

## Reference Tables
| Framework | Feature                  | Example Use Case                     |
|-----------|--------------------------|------------------------------------|
| Apache Flink    | Batch processing      | Web application with near-zero latency |
| Kafka         | Message passing       | Distributed real-time applications          |
| H2            | Low-latency storage   | High-throughput, low-latatum data systems  |
| Samza        | Batch processing      | Complex event-driven applications           |

## Key Takeaways
1. Use Apache Flink for high-throughput stream processing and fault tolerance.
2. Leverage Kafka for real-time messaging in distributed systems.
3. Utilize H2 for low-latency, high-performance data storage.
4. Apply event sourcing to maintain causality in distributed systems.
5. Avoid using a global clock and ensure causality through idempotent operations.

## Connects To
- Relates to Chapter 8 on Event Processing for Data Stores as it discusses similar concepts of causality and temporal ordering.
- Connects to Chapter 9 on Time-Based Architecures as it explains how time is managed in distributed systems.