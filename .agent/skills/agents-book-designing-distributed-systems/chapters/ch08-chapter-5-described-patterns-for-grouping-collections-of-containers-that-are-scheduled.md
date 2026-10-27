# Chapter 8: Microservices Architecture

## Core Idea  
Microservices provide a scalable, flexible, and maintainable architecture by breaking down applications into loosely coupled components that communicate via APIs.

## Frameworks Introduced  
- **Microservices**: A system built from many components running in separate processes, each providing a specific service through defined APIs.  
  - When to use: When you need flexibility, scalability, and decoupling between services.  
  - How: Break an application into smaller, single-responsibility services that interact via well-defined interfaces.

## Key Concepts  
- **Microservices**: A collection of loosely coupled components providing specific functionalities through APIs.  
- **Monolithic System**: A single, tightly integrated application with all functionalities contained within a single container.  
- **Encapsulation**: Hiding implementation details while exposing service interfaces for use by other components.  
- **Abstraction**: Focusing on high-level capabilities without delving into detailed implementations.  
- **Decoupling**: Reducing tight synchronization between services to enable independent management and iteration.  
- **Statelessness**: A characteristic of some microservices that allows them to scale horizontally without maintaining internal state.

## Mental Models  
Use microservices when you want to balance flexibility, scalability, and maintainability. Think of a microservice as a service that focuses on a single responsibility with a well-defined API interface.

## Anti-patterns  
- **Over-segmentation**: Dividing services into too many small components, leading to inefficiency and complexity.  
  - Why it fails: Increases overhead, network traffic, and management effort without significant benefits in scalability or maintainability.

## Code Examples  
```java
public interface ServiceInterface {
    <return type> serviceMethod(<argument types>);
}

public class UserService implements ServiceInterface {
    @ServiceLoader(ServiceLoader.class)
    public static Service load() { ... }
}
```
- **What it demonstrates**: The use of a well-defined API (ServiceInterface) to encapsulate service functionality and enable decoupling.

## Reference Tables  
| Parameter          | Value/Decision               |
|--------------------|------------------------------|
| When to Use       | Break down monolithic systems into smaller, focused services. |
| How to Implement  | Use APIs for communication; implement microservices patterns like synchronous/asynchronous messaging. |

## Key Takeaways  
1. Use microservices when you need flexibility and scalability in your application architecture.
2. Encapsulation and abstraction enable teams to work independently on different components.
3. Decoupling allows services to be scaled independently without affecting the entire system.

## Connects To  
- Relates to distributed patterns discussed earlier, such as loosely coupled systems and defined communication interfaces.