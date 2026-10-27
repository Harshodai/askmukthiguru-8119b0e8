# Chapter 12: Functions and Event-Driven Processing

## Core Idea
Functions as a Service (FaaS) is a powerful approach for building event-driven applications that require scalability, flexibility, and efficient resource management. It allows developers to deploy simple functions that handle specific tasks while abstracting away the underlying infrastructure.

## Frameworks Introduced
- **Decorator Pattern**: A design pattern used to add responsibilities to objects by wrapping them in stateless decorators.  
  - When to use: To incrementally enhance HTTP or RESTful APIs with features like validation, default values, and event handling.
  - How: Wrap an input request with a decorator function that performs additional processing before passing it on to the main service.

## Key Concepts
- **FaaS**: A model where functions are executed in response to discrete events. It is serverless but not always serverless due to its ability to handle long-running computations and maintain state.
- **5 Whys**: A problem-solving technique used to dig deeper into root causes by asking "Why" multiple times.

## Mental Models
- Use the Decorator Pattern when you need lightweight decoupling of features without major architectural changes. It helps in maintaining modularity while adding functionality incrementally.

## Anti-patterns
- Overloading FaaS with sustained request processing can lead to inefficiencies and scalability issues.
- Avoid using FaaS for background tasks that require strict control over resources or state, as it may not be suitable for such scenarios due to its inherent limitations.

## Code Examples
```python
def handler(context):
    # Perform additional logic before passing the request to the main service
    return {"status": "ok"}
```

This code demonstrates how a decorator function can take an input context (e.g., JSON payload) and perform additional processing before delegating it to another service.

## Reference Tables

| Feature                | FaaS                          | Serverless Computing          |
|-----------------------|-------------------------------|------------------------------|
| Event-driven         | Yes                            | Typically synchronous        |
| State management      | Limited                       | Full state management       |
| Long-running tasks   | Can be handled with care     | Not typically supported    |
| Scalability          | High                           | Depends on infrastructure  |

## Key Takeaways
1. Use FaaS for event-driven or asynchronous needs where lightweight functions suffice.
2. Decorate HTTP requests to add features like defaulting values without major architectural changes.
3. Recognize when overloading FaaS with sustained request processing can lead to inefficiencies.

## Connects To
- Chapter 9: Function-as-a-Service
- Chapter 10: Background Processing and State Management