# Chapter 3: Social Network Home Timelines  

## Core Idea  
The chapter emphasizes the importance of defining nonfunctional requirements to ensure system reliability, scalability, performance, and security in large-scale applications like social networks.

## Frameworks Introduced  
- **Fanout**: A framework for understanding data replication and its impact on throughput.  
  - When to use: To analyze how fan-out affects system performance and identify bottlenecks.  
  - How: Calculate the number of requests a single source can handle before the system becomes overwhelmed.  

## Key Concepts  
- Nonfunctional requirements: Performance, scalability, availability, and security.  
- Fanout: The number of times data is replicated across systems to ensure reliability.  
- Response time: The delay between when a request is received and when it's processed.  
- Percentile metrics (e.g., p95, p99): Used to measure system performance under load.  

## Mental Models  
- Use **fanout** when analyzing data replication strategies in distributed systems.  
- Prioritize **response time metrics** over throughput when designing for user experience.  
- Apply **percentile-based SLOs (Service Level Agreements)** to ensure consistent performance levels.  

## Anti-patterns  
- Avoid poor error handling that leaves faults unhandled, leading to system failures.  
- Be cautious of network latency causing slow response times, which can degrade user experience.  

## Code Examples  
```sql
SELECT posts.*, users.* FROM posts
  JOIN follows ON posts.sender_id = follows.followee_id
  JOIN users ON posts.sender_id = users.id
  WHERE follows.follower_id = current_user;
```
- **What it demonstrates**: The SQL query for fetching recent posts by a user, highlighting how nonfunctional requirements impact database design and query performance.  

## Reference Tables  
### Decision Matrix: Throughput vs. Response Time  
| Metric               | Impact on Scalability | Impact on User Experience |
|----------------------|-----------------------|---------------------------|
| Throughput            | Directly affects system load | No noticeable impact        |
| Response Time         | Affects user satisfaction | High impact                |

### Table of Key Metrics and When to Use Them  
| Metric          | When to Use                     | Example Use Case               |
|-----------------|-------------------------------|------------------------------|
| p95             | For systems requiring high availability  | 95% uptime for critical services |
| p99             | For systems with high reliability requirements | 99% error-free performance     |
| p99.9           | For mission-critical systems    | Financial institutions        |

## Key Takeaways  
1. Prioritize response time metrics to ensure user satisfaction in social networks.  
2. Use percentile-based SLOs (e.g., p95, p99) to define nonfunctional requirements for reliability and availability.  
3. Understand the trade-offs between throughput and response time when designing distributed systems.  

## Connects To  
- Distributed Systems (Chapter 6)  
- Load Balancing and Scalability (Chapter 4)