# Cheatsheet

### Cheatsheet: AI Infrastructure and Container Grouping Strategies  
This cheatsheet provides decision tables, comparison matrices, and quick reference rules for practitioners working with AI infrastructure and container grouping strategies.  

---

#### **Decision Table: Choosing the Right AI Infrastructure**  
| **Criteria** | **Options** |  
|--------------|-------------|  
| **Use Case** | **AI Infrastructure Needed** |  
| Small-scale projects | Lightweight frameworks (e.g., TensorFlow Lite, PyTorch Lightning) |  
| Medium to large-scale projects | Scalable frameworks (e.g., TensorFlow, PyTorch) with distributed training support |  
| Real-time inference applications | Optimized frameworks for inference (e.g., ONNX Runtime, TensorRT) |  

---

#### **Comparison Matrix: Container Grouping Patterns**  
| **Criteria** | **Patterns** |  
|--------------|-------------|  
| **Scheduling Efficiency** | |  
| - High CPU utilization | Long pipelines or task parallelism |  
| - Low memory usage | Short pipelines or microservices architecture |  

| **Scalability** | |  
| - Horizontal scaling | Elastic Kubernetes clusters (e.g., AWS EC2, Azure Kubernetes Service) |  
| - Vertical scaling | Container orchestration tools (e.g., Docker Compose, Kubernetes) |  

| **Security** | |  
| - Container isolation | Containerization toolset (e.g., Docker, Virtual Machines) |  
| - API security | Secure APIs and authentication mechanisms (e.g., OAuth 2.0, JWT) |  

---

#### **Quick Reference Rules for AI Development**  
1. **AI Model Deployment**  
   - Use lightweight frameworks for small-scale projects to minimize deployment overhead.  
   - Use scalable frameworks with distributed training for large-scale projects.  

2. **Container Grouping**  
   - For high CPU utilization: Implement long pipelines or task parallelism.  
   - For low memory usage: Optimize the application architecture and use short pipelines or microservices.  

3. **Orchestration**  
   - Use Kubernetes for horizontal scaling.  
   - Use Docker Compose or Kubernetes for vertical scaling.  

4. **Security Best Practices**  
   - Always enable container isolation with containerization tools like Docker or Virtual Machines.  
   - Implement secure APIs and authentication mechanisms (e.g., OAuth 2.0, JWT) for API security.  

---

This cheatsheet provides a concise reference for practitioners to make informed decisions about AI infrastructure and container grouping strategies based on their specific needs.