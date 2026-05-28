# Chapter 22: A Philosophy of Streaming Systems

## Core Idea
The single most important thing this chapter teaches is that streaming systems provide a practical solution to the limitations of traditional relational databases in handling high-throughput, low-latency applications.

## Frameworks Introduced
- **EventSourcing**: A method for real-time data synchronization using events and streams. Used when dealing with event-driven architectures or microservices.
  - When to use: Event-driven systems requiring real-time updates.
  - How: Synchronize data changes through events, ensuring atomic commits and rollbacks.

- **Dataflow Programming with Streams**: An approach where data flows through a pipeline of transformations for real-time processing. Used in applications requiring ordered data transformation pipelines.
  - When to use: High-throughput streaming platforms like Apache Flink or Kestrel.
  - How: Define data transformations as a series of stages in a dataflow graph.

- **Asynchronous Transactional Systems (ATS)**: Designed for non-blocking, atomic operations on event streams. Used when building fault-tolerant, real-time distributed systems.
  - When to use: Distributed applications requiring low-latency, high-throughput transactional reliability.
  - How: Implement non-blocking reads/writes with atomic commits and checkpoints.

## Key Concepts
- **EventSourcing**: "The minimal observable change in the application's state when an event is processed." A precise definition of event-driven architecture.
- **Dataflow Programming**: "A programming model for expressing data transformations as a directed acyclic graph (DAG) of events, where each node represents a transformation function and edges represent dependencies between events."
- **Asynchronous Transactional Systems**: "An approach to building transactional systems by using non-blocking reads and writes that are idempotent in nature."

## Mental Models
Think of streaming systems as:
- A solution for real-time data synchronization when traditional databases fail due to throughput or latency constraints.
- An architecture for microservices where each service can process events independently while maintaining state consistency.

## Anti-patterns
- **Microbatching**: Can lead to stale data in event-driven architectures. Avoid by ensuring atomic commits and checkpoints.
- **Lack of Transaction Validation**: Transactions may appear successful but fail at checkpoint, leading to rollbacks. Avoid by validating transactions before checkpointing.

## Code Examples
```
key code example
```

```python
# Example EventSourcing Implementation
from typing import Optional

class EventSource:
    def __init__(self):
        self.events = []
    
    def append_event(self, event: dict) -> None:
        self.events.append(event)
        
    def get_events(self) -> list[dict]:
        return self.events.copy()
```

```rest api example
import requests
from time import sleep

class RESTAPI:
    def __init__(self):
        self URL = "http://localhost:8080/api"
    
    async def fetch_stream(self, endpoint: str) -> list[dict]:
        results = []
        while True:
            response = await requests.get(f"{self.URL}/{endpoint}")
            if response.status_code == 200:
                data = response.json()
                results.extend(data.get('stream', []))
                sleep(1)
            else:
                raise Exception("Failed to fetch stream")
        return results

    async def process_stream(self, event: dict) -> None:
        for item in self.fetch_stream(endpoint="stream"):
            print(f"Processing {event['timestamp']}")

async def main():
    async with RESTAPI() as api:
        await api.process_stream(event)
```

## Reference Tables
| **Decision Matrix** | **Criteria**                     |
|--------------------|----------------------------------|
| Relational Database   | Throughput: Low, Latency: High       |
| EventSourcing         | Throughput: High, Latency: Low     |
| Dataflow Programming  | Throughput: Very High, Latency: Medium |
| ATS                  | Throughput: High, Latency: Low      |

## Key Takeaways
1. Use streaming systems for real-time data synchronization in microservices.
2. Leverage event-driven architectures for IoT applications requiring low-latency updates.
3. Implement microservices with streams to handle high-throughput, real-time workloads.
4. Validate transactions before checkpointing to avoid rollbacks and stale data.
5. Use event sourcing for real-time analytics in distributed systems.

## Connects To
- **Chapter 2**: Dataflow programming concepts
- **Chapter 3**: Event-driven architectures
- **Chapter 10**: Microservices design principles