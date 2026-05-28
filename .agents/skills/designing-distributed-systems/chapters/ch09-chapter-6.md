# Chapter 9: replicated load-balanced services

## Core Idea
This chapter teaches how to create highly available, scalable, and efficient web services using replicated load-balanced architecture, including replication, load balancing, caching, and SSL termination.

## Frameworks Introduced
- **Replicated Load-Balanced Stateless Services**: Uses multiple identical instances with a load balancer to distribute traffic. Benefits include high availability, performance scaling, and resilience.
  - When to use: When building scalable web services that require high uptime and fault tolerance.
  - How: Replicate the service across multiple nodes, use a load balancer to distribute requests, and ensure each replica is identical.

## Key Concepts
- **Stateless Service**: A service where no data persists between requests. Each request is independent of previous ones.
- **Replication**: Sending traffic to multiple instances (replicas) to ensure redundancy and fault tolerance.
- **Load Balancing**: Distributing traffic across replicas using a load balancer to balance request load, latency, or uptime.
- **Readiness Probe**: Determines if an application is ready to serve requests by checking network connectivity between containers.
- **Consistent Hashing**: A method for distributing keys (e.g., requests) across a set of nodes in a cluster while maintaining high availability and minimizing the impact of node failures.

## Mental Models
- Use replication when you need high availability and fault tolerance. Think of it as having multiple identical workers to handle traffic.
  - When to use: When building scalable web services that require high uptime and fault tolerance.
  - How: Replicate the service across multiple nodes, use a load balancer to distribute traffic, and ensure each replica is identical.

## Anti-patterns
- **Over-reliance on a single instance without proper scaling**: Can lead to performance degradation or failures if not properly handled. For example, using a single instance for a high-traffic service without replicating across multiple nodes.
  - What to avoid: Relying too heavily on a single server without considering scalability and redundancy.

## Code Examples
```kotlin:dictionary-deploy.yaml
apiVersion : extensions/v1beta1
kind: Deployment
metadata:
  name: dictionary-server
spec:
  replicas : 3
  template :
    metadata :
      labels:
        app: dictionary-server
    spec:
      containers :
      - name: server
        image: brendanburns/dictionary-server
        ports:
        - containerPort : 8080
        readinessProbe :
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds : 5
          periodSeconds : 5
Y ou can create this replicated service with:
kubectl create -f dictionary-deploy.yaml
```

## Reference Tables

| Term                  | Definition                                                                 |
|----------------------|-----------------------------------------------------------------------------|
| Stateless Service     | A service where no data persists between requests. Each request is independent of previous ones. |
| Replication           | Sending traffic to multiple instances (replicas) to ensure redundancy and fault tolerance. |
| Load Balancing        | Distributing traffic across replicas using a load balancer to balance request load, latency, or uptime. |
| Readiness Probe       | Determines if an application is ready to serve requests by checking network connectivity between containers. |
| Consistent Hashing     | A method for distributing keys (e.g., requests) across a set of nodes in a cluster while maintaining high availability and minimizing the impact of node failures. |

## Key Takeaways
1. Use replicated load-balanced stateless services when building scalable web services that require high uptime and fault tolerance.
2. Implement replication by replicating the service across multiple nodes, using a load balancer to distribute traffic.
3. Utilize consistent hashing for distributing requests across replicas while maintaining availability and minimizing impact of node failures.
4. Caching can improve performance without breaking session tracking or functionality.

## Connects To
- Previous chapters on Kubernetes deployment patterns
- Next chapters on advanced load balancing techniques