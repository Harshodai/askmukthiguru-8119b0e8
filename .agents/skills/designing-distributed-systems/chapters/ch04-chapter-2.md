```markdown
# Chapter 4: Core Concepts of Distributed Systems

## Core Idea
APIs are the foundation of distributed systems due to their ability to support Service Level Objectives (SLOs) and scale horizontally.

## Frameworks Introduced
- **RESTful APIs**: Defined by HTTP verbs, resource-based URLs, and well-known operational procedures.  
  - When to use: For simple, scalable web services with RESTful principles.
  - How: Implement via frameworks like Django or Flask in Python.

- **gRPC (Google Protobuf REST over Protocol Buffers)**: A high-performance messaging protocol for distributed systems.  
  - When to use: For high-throughput and low-latency applications requiring complex data types.
  - How: Use gRPC over HTTP(S) with a transport layer like WireGuard or HTTP2.

## Key Concepts
- **Service Level Objectives (SLOs)**: Metrics like 99.9% uptime ensure consistent performance for end-users.
- **Latency**: Measures time-to-event in distributed systems; critical for real-time applications.
- **Reliability**: Ensures high availability and minimal downtime through redundancy and failover mechanisms.
- **Idempotency**: Guarantees a business operation can be retried without side effects, crucial for APIs.
- **Delivery Semantics**: Differentiates "at least once" (eventual consistency) from "at most once" (strong consistency).
- **Relational Integrity**: Ensures data consistency across distributed databases like SQL and NoSQL.
- **Data Consistency**: Combines strong or eventual consistency with transaction management for reliable state updates.

## Mental Models
- Use RESTful APIs when you need a simple, scalable service with SLO support.  
- Apply idempotent operations to avoid failures during retries.  
- Opt for eventual consistency in large-scale systems due to performance trade-offs.

## Anti-patterns
- **Non-idempotent operations**: Can cause bottlenecks if not properly handled.
- **Overcommitment of resources**: Leads to degraded performance and system instability.
- **CAP Theorem limitations**: Trade off availability, consistency, and partition tolerance in distributed systems.

## Code Examples
```python
from fastapi import HTTPException

class ApiService:
    def __init__(self):
        self.status = "idle"
    
    async def get(self, id: int):
        if self.status != "idle":
            raise HTTPException(status_code=503, detail="Service is not idle")
        self.status = "processing"
        result = await self.process(id)
        return {"status": "success", "data": result}
    
    async def post(self, id: int):
        if self.status != "idle":
            raise HTTPException(status_code=503, detail="Service is not idle")
        self.status = "processing"
        result = await self.process(id)
        return {"status": "success", "data": result}
```

This code demonstrates a RESTful API with idempotent operations to prevent race conditions.

## Reference Tables
| **Term**         | **Definition**                                                                 |
|-------------------|-----------------------------------------------------------------------------|
| Service Level Objective (SLO) | A measurable metric that defines system performance, such as 99.9% uptime. |
| Latency            | Time-to-event for a request completion in distributed systems.                |
| Reliability        | Ensures high availability and minimal downtime through redundancy mechanisms.   |
| Idempotency        | A property of operations where retrials do not affect the system state.     |

## Key Takeaways
1. Choose RESTful APIs when you need scalability and SLO support.
2. Understand SLOs to design systems with measurable performance guarantees.
3. Use idempotent operations to handle retries reliably without side effects.

## Connects To
- Chapter 5: Single-Node Patterns  
- Chapter 6: Orchestrators and Kubernetes
```