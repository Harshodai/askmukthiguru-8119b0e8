# Cheatsheet

### Cheatsheet: System Design and Distributed Systems  

---

#### **Decision Table for Choosing a Database or Architecture**  
| **Key Decision** | **Options** | **Recommendation (from Chapters)** |  
|------------------|-------------|------------------------------------|  
| Should I use ACID or CAP? | - ACID (Atomic, Consistent, Isolated, Durable) <br> - CAP (Conflict-Aware, Persistent, Atomic) | - Use ACID if strong consistency and durability are critical. <br> - Use CAP when availability is more important than strict consistency. |  
| Should I use a relational database or NoSQL? | - Relational databases (e.g., PostgreSQL, MySQL) <br> - NoSQL databases (e.g., MongoDB, DynamoDB) | - Use relational databases for structured data with predictable schema. <br> - Use NoSQL databases for unstructured data and scalability. |  
| Should I implement horizontal scaling? | - Yes <br> - No | - Horizontal scaling is essential for load growth in distributed systems (Chapter 12). <br> - Consider vertical scaling if horizontal scaling is not feasible. |  

---

#### **Comparison Matrix: System Types vs. Features**  
| **System Type** | **Scalability** | **Consistency** | **Availability** | **Fault Tolerance** |  
|-----------------|-----------------|------------------|-------------------|-----------------------|  
| Relational DB   | High            | High              | High               | Moderate               |  
| NoSQL (DynamoDB)| Moderate        | Low               | High               | High                   |  
| Distributed System | Very High       | Low/Medium        | Low                | High                   |  

---

#### **Quick Reference Rules for Practitioners**  
1. Always ensure ACID compliance in critical live processes to maintain data integrity (Chapter 5).  
2. Use CAP instead of ACID when high availability is required but strict consistency is not critical (Chapter 9).  
3. For distributed systems, prioritize horizontal scaling over vertical scaling (Chapter 12).  
4. Implement conflict detection and rollback mechanisms in NoSQL databases to ensure data integrity (Chapter 10).  
5. Use event-driven architecture for real-time applications requiring low latency (Chapter 6).  

---

#### **Summary**  
- **Relational Databases**: Best for structured, predictable workloads with high consistency and durability.  
- **NoSQL Databases**: Ideal for unstructured data, scalability, and flexibility.  
- **Distributed Systems**: Optimize for horizontal scaling, fault tolerance, and low latency using techniques like DynamoDB or Riak.  

This cheatsheet provides a concise reference to key system design principles and best practices discussed in the chapters.