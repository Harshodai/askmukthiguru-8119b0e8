This guide details the implementation of a dual-memory system (short-term and long-term) for AI agents using **LangGraph** and **Neo4j**, as demonstrated by Homayoun, a tech co-founder and video analyst.

### **1. Implementation Architecture**
The system uses a **React Agent** architecture. The core logic is managed by LangGraph, while Neo4j serves as the persistent Knowledge Graph (KG).
*   **Short-term Memory:** Thread-scoped, tracking the immediate conversation flow.
*   **Long-term Memory:** User-scoped, persisting across different sessions by storing data in Neo4j.
*   **Components:** The agent interacts with tools, a Knowledge Graph, and an output parser to provide structured responses.

### **2. Memory Extraction & Graph Updates**
Memory is extracted from user interactions and stored as nodes in Neo4j.
*   **Data Structure:** Memory nodes include a `key`, `namespace` (combining `user_id` and `thread_id`), `value` (the message content), and a `timestamp`.
*   **Cypher Implementation:** The system uses the `MERGE` command to update or create memory nodes:
    ```cypher
    MERGE (m:Memory {namespace: $ns, key: $key})
    SET m.value = $val, m.timestamp = $ts
    ```
*   **Process:** Every new user message is timestamped and saved to the graph before the LLM generates a response.

### **3. Retrieval & Entity Resolution**
Retrieval is handled via a `search_memory` method that pulls historical context based on the user's identity.
*   **Context Injection:** The system retrieves the last five memories from Neo4j, orders them by timestamp (descending), and converts them into a dictionary for the Python environment.
*   **State Modification:** LangGraph’s `state_modifier` is used to rebuild the system prompt dynamically, prepending the retrieved long-term memories to the current message list.

### **4. Privacy & Session Isolation**
Privacy is enforced through strict namespacing.
*   **User Identification:** Memory is partitioned using a `user_id`.
*   **Isolation Test:** The video demonstrates that if the `user_id` is changed (e.g., from `user_id = "Homayoun"` to `user_6`), the agent correctly states, *"I do not have information about your name,"* even if the name was just stored under a different ID.

### **5. Concrete Code & System Practices**
*   **Short-term Storage:** Use `langgraph.checkpoint.memory.MemorySaver()` for thread-scoped check-pointing.
*   **Long-term Storage:** Create a custom `Neo4jMemoryStore` class with `put_memory` and `search_memory` methods.
*   **Agent Creation:** Pass the memory stores into the `create_react_agent` function:
    *   `checkpointer`: Handles short-term memory.
    *   `state_modifier`: A function (e.g., `load_and_save_long_term`) that manages the Neo4j I/O and prompt augmentation.
*   **UI Testing:** Use **Streamlit** to create a chatbot interface for real-time testing of memory persistence across session restarts.

### **6. Key Quotes**
*   "Short-term is for tracking the conversation in session, and long-term memory is for saving the entire conversation for a specific user into the knowledge graph."
*   "Database file defines a new class that connects to Neo4j for saving and retrieving information."
*   "Put memory method stores a memory into the Neo4j under a specific namespace."
*   "Search memory retrieves the last few conversations and returns it to the Python as a dictionary."
*   "Long-term memory function does three main important things: first it saves the latest user message... second it loads the last five memories... and finally builds a new messages using system prompt, memories list, and current chat messages."
*   "When we change the user ID, the agent shouldn't remember my name anymore."