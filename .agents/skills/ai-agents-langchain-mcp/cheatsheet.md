# Cheatsheet

### AI Agent Development Cheatsheet: Decision Tables, Comparison Matrices, and Quick Reference Rules  

---

#### **Decision Tables**  
| **Decision** | **Action/Recommendation** |  
|--------------|---------------------------|  
| Need to implement an AI agent? | Start with the basics (Chapters 2–4) to understand the fundamentals. |  
| Should I use memory or no memory for my agent? | Use memory if you need to retain information across interactions; otherwise, disable it. |  
| What retrieval strategy should I use? | Start with linear search and then implement a vector store (like FAISS) for faster results. |  
| Do I need guardrails in my AI system? | Always enable guardrails to ensure safety and accountability. |  
| Should I deploy on-premise or cloud? | Use cloud services like AWS, Azure, or GCP for scalability and cost-efficiency. |  

---

#### **Comparison Matrices**  
| **Tool/Feature** | **Description** | **Use Case** |  
|------------------|-----------------|--------------|  
| LangChain        | Framework for building AI applications using tools like LLMs, connectors, and memory. | Ideal for rapid prototyping of AI agents. |  
| OpenAI          | Leading open-source LLM provider (GPT-4, GPT-3.5). | Best for small-scale projects or research purposes. |  
| Hugging Face      | Platform for state-of-the-art NLP models and tokenizers. | Suitable for custom model integration. |  
| SQLite           | Lightweight database for storing document chunks. | Efficient for small-scale data storage. |  

---

#### **Quick Reference Rules**  
1. Always enable memory in your AI agent to improve contextual understanding over time.  
2. Use guardrails to ensure safe and explainable interactions with the system.  
3. Start with linear search and then implement a vector store (e.g., FAISS) for faster retrieval.  
4. For small-scale projects, use OpenAI or LangChain with pre-trained models.  
5. Use SQLite for efficient document storage in local environments.  

---

#### **Common Pitfalls to Avoid**  
1. Forget to enable guardrails, leading to unpredictable or unsafe interactions.  
2. Over-reliance on linear search; switch to vector stores for faster results as your dataset grows.  
3. Neglecting memory retention settings, which can degrade the agent’s contextual understanding over time.  
4. Underestimating the need for proper documentation and testing before deployment.  

---

#### **Summary**  
- Start with the basics (Chapters 2–4) to understand AI agent fundamentals.  
- Use LangChain for rapid prototyping and integrate memory, guardrails, and retrieval strategies.  
- Choose appropriate tools based on your use case: OpenAI for small-scale projects, Hugging Face for custom models, and SQLite for local data storage.  

This cheatsheet provides a concise reference for practitioners developing AI agents, covering key decisions, comparisons, and best practices to ensure success in building robust and reliable systems.