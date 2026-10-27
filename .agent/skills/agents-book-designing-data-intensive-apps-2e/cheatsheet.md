# Cheatsheet

### Cheatsheet for Database Transactions

This cheatsheet provides decision tables, comparison matrices, and quick reference rules to help practitioners choose the right database for their transaction needs.

---

#### **Decision Table: Transaction Support**
| **Feature**          | **PostgreSQL** | **MySQL**   | **SQL Server** | **VoltDB**     |
|-----------------------|---------------|-------------|----------------|---------------|
| ACID Compliance       | Yes           | Yes         | Yes            | Yes           |
| Sharding              | No            | No          | No             | Yes           |
| Parallelism           | No            | No          | No             | Yes           |
| Caching Mechanisms    | No            | No          | Yes            | Yes           |

---

#### **Comparison Matrix: Transaction Strengths**
| **Database**       | **ACID Compliance** | **Scalability (Sharding)** | **Parallelism** | **Caching**   | **Performance** |
|--------------------|----------------------|---------------------------|-----------------|---------------|-----------------|
| PostgreSQL        | Yes                  | No                        | No               | No             | High            |
| MySQL              | Yes                  | No                        | No               | No             | Moderate        |
| SQL Server         | Yes                  | No                        | No               | Yes            | High            |
| VoltDB            | Yes                  | Yes                       | Yes              | Yes            | Very High      |

---

#### **Quick Reference Rules**
1. **Use ACID-compliant databases for critical transactions**:
   - PostgreSQL, MySQL, SQL Server, and VoltDB all support ACID.
   - Choose based on other factors like scalability or caching needs.

2. **For sharding (distributing across multiple nodes)**:
   - Use VoltDB if you need both sharding and ACID compliance.

3. **For parallelism in transaction processing**:
   - SQL Server supports parallelism for complex queries.
   - VoltDB also supports parallelism with caching.

4. **For high-performance, read-heavy transactions**:
   - SQL Server and VoltDB are optimized for such scenarios due to their caching mechanisms.

---

### **Key Takeaway**
- Choose a database based on transaction requirements (ACID, scalability) and system architecture (single-node vs. distributed).

This cheatsheet provides a concise guide to help you make informed decisions about database transactions.