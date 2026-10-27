# Chapter 5: Chapter 7 .

## Core Idea
The chapter emphasizes that not all systems are equal, highlighting the importance of choosing the right architecture for maintaining maintainability, scalability, and evolvability over time.

## Frameworks Introduced
- **Performance**: Using principles like horizontal scaling and microservices to ensure systems can handle increased workloads.
  - When to use: Optimal for systems requiring high availability and performance.
  - How: Implementing horizontal scaling strategies and breaking down monolithic architectures into smaller, independent services.
  
- **Reliability**: Incorporating fault-tolerance mechanisms such as replication, checkpointing, and heartbeats.
  - When to use: For systems with critical operations where downtime is unacceptable.
  - How: Using techniques like quorum-based replication for high availability and implementing heartbeat mechanisms.

- **Complexity**: Simplifying systems through abstraction layers, standard patterns, and domain-driven design.
  - When to use: For systems requiring simplicity in maintenance and evolution.
  - How: Applying patterns such as layered architectures and breaking down complex systems into smaller components.

## Key Concepts
- **Performance Metrics**: Defined using percentiles (e.g., 95th percentile) to measure response time distributions.
- **Reliability Techniques**: Implementing mechanisms like load balancing, replication, and checkpointing for high availability.
- **Complexity Management**: Using abstraction layers and standard patterns to simplify system design.

## Mental Models
- Use microservices architecture when you need to scale horizontally or maintainability over time.
- Apply domain-driven design principles to ensure systems are built with the right abstractions and patterns.

## Anti-patterns
- Avoid monolithic architectures due to scalability issues, poor maintainability, and difficulty in evolution.

## Code Examples
```python
from redis import Redis

r = Redis(host="localhost", port=6379)

async def load_balancer(workers: List[str], requests: List[Dict]) -> Dict:
    results = {w: {"count": 0} for w in workers}
    async with asyncio.to_thread(asyncio.sleep) as sleep:
        while True:
            await sleep
            total = sum(req["req"] for req in requests)
            if total == 0:
                break
            await asyncio.sleep(1 / max(total, 1))
            results = {w: {"count": 0} for w in workers}
            for req in reversed(requests):
                dest = req["to"]
                results[dest]["count"] += req["req"]
    return results
```
- **What it demonstrates**: An efficient load balancing mechanism using Redis and asyncio to distribute requests across workers.

## Reference Tables
| Parameter | Description |
|-----------|-------------|
| `workers`  | List of worker nodes |
| `requests` | List of request dictionaries with "to" (worker) and "req" (number of requests) |

## Key Takeaways
1. Choose the right architecture for your system's requirements to ensure maintainability, scalability, and evolvability.
2. Implement performance metrics like response time percentiles to optimize systems.
3. Use reliability techniques such as replication and checkpointing to handle failures gracefully.

## Connects To
- Relates to discussions on maintaining simplicity in design (Chapter 6) and system evolution strategies (Chapter 8).