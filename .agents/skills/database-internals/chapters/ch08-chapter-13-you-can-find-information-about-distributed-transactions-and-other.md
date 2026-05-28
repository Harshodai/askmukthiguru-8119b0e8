# Chapter 8: Transaction Processing and Recovery

## Core Idea
Understanding transaction isolation levels is crucial for ensuring correctness in distributed systems while maintaining high concurrency. This involves choosing the appropriate level of atomicity (e.g., serializability, linearizability) and employing robust concurrency control mechanisms to handle potential anomalies.

---

### Frameworks Introduced
- **MVCC (Multi-Version Concurrent Control)**:  
  - When to use: Implementing snapshot isolation in distributed systems.
  - How: Uses version numbers to ensure consistent reads and detect conflicting operations during writes.

### Key Concepts
- **Isolation Level**: Determines the degree of atomicity for transactions, e.g., serializability (strongest) or read-ahead (weakest).
- **ACID Properties**: Ensures transactions are Atomic, Consistent, Isolated, and Durable.
- **Lock-Based Concurrency Control**: Includes two-phase locking (2PL), three-phase locking (3PL), and pessimistic/optimistic approaches.

### Mental Models
- Use readers-writer locks when concurrency control needs to balance performance and correctness. For example, in a high-throughput database system, this approach minimizes contention while ensuring transactional integrity.

### Anti-patterns
- **Optimistic Concurrency Control**: Can lead to deadlocks if multiple transactions attempt to acquire exclusive locks simultaneously.
- **Snapshot Isolation**: Fails when partial writes occur because it cannot handle incomplete state changes during a transaction rollback.

### Code Examples
```java
public class Transaction {
    private final int txId;
    private final long commitTime;
    private final long startRead;
    private final long endRead;

    public Transaction(long commitTime, long startRead) {
        this.commitTime = commitTime;
        this.startRead = startRead;
        this.endRead = System.currentTimeMillis();
        txId = GenerateTxId();
    }

    public void begin() {
        // Log statements for optimistic concurrency control
        if (ts1 > nlock) { 
            // Write a log indicating the transaction is in progress
            writeLog("locking", lock);
            // Check if we can proceed without locking
            if (nlock == 0 && ts2 > nlock) {
                // We can lock ourselves now and release existing locks later
                lock = true;
            }
        } else { 
            // Lock the transaction
            lock = true;
        }

        // Log a commit to ensure serializability
        log("commit", this);
    }

    public void read(final long key) {
        if (nlock == 0 || startRead > commitTime) {
            // Read is safe since no locks are held
            read(key);
        }
    }

    public void rollback() {
        // Log a rollback to ensure serializability
        log("rollback", this);
        
        // Revert all operations in the transaction
        try {
            for (int i = txId; i > lockId; --i) {
                if (lock[i] == false) break;
                lock[i] = false;
            }
            commitTime = 0;
            txId = lockId;
        } catch (Exception e) {
            // Log the exception
            log("rollbackError", this, e);
        }
    }

    public void commit() {
        // Log a commit to ensure serializability
        log("commit", this);

        try {
            commit();
            // Re-write all versions of the transaction history
            for (int i = txId; i > lockId; --i) {
                if (lock[i] == false) break;
                writeLog("write", lock);
                lock[i] = true;
            }
        } catch (Exception e) {
            // Log the exception
            log("commitError", this, e);
        }
    }

    private static final long lockId = 1L;

    protected synchronized Object log(Object what, Lock lock) {
        if (lock == null || lock != lockId) {
            throw new IllegalStateException("Cannot use another lock during logging");
        }
        try {
            // Implement logging mechanism
            return log;
        } catch (Exception e) {
            // Log the exception
            log("logError", this, e);
            throw e;
        }
    }

    protected synchronized Object commit() {
        if (commitTime == 0) {
            throw new IllegalStateException("Cannot commit a transaction that was not started");
        }
        try {
            commit();
            return commit;
        } catch (Exception e) {
            // Log the exception
            log("commitError", this, e);
            throw e;
        }
    }

    protected synchronized Object rollback() {
        if (txId == lockId) {
            throw new IllegalStateException("Cannot rollback a transaction that was not started");
        }
        try {
            rollback();
            return commit;
        } catch (Exception e) {
            // Log the exception
            log("rollbackError", this, e);
            throw e;
        }
    }
}
```

### Reference Tables

| **Concurrency Control Method** | **Allowed Anomalies** |
|-------------------------------|------------------------|
| Read-Ahead                     | Lost Update           |
| Nonrepeatable Read              | Phased Write          |
| Unread Write                    | Write Skew            |

---

### Key Takeaways
1. Use MVCC for implementing snapshot isolation in distributed systems.
2. Choose an appropriate concurrency control mechanism based on system requirements and performance constraints.
3. Avoid optimistic concurrency that can lead to deadlocks.

---

### Connects To
- Distributed transactions (Chapter 13)