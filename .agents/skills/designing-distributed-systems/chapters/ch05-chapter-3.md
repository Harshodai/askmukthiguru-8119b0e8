# Chapter 5: The Sidecar Pattern

## Core Idea
The sidecar pattern enables extending legacy applications with additional functionality without major changes to their core logic by using two containers: an application container and a sidecar container.

## Frameworks Introduced
- **Sidecar Pattern**: 
  - When to use: To extend legacy applications or add new features without modifying the original codebase.
  - How: By creating a sidecar container that augments the application container with additional functionality, such as dynamic configuration management, monitoring, or adding new features like HTTPS.

## Key Concepts
- **Sidecar Container**: A secondary container that extends the capabilities of an application container while sharing resources and process IDs (PIDs) with it.
- **Parameterization**: Customizable containers that can be configured with specific parameters to adapt to different use cases.
- **Modular Reusability**: Designing sidecars as reusable components that can be easily integrated into various applications.

## Mental Models
Use the sidecar pattern when you need to add functionality to an existing application without disrupting its core logic. Think of it as a bridge between your legacy system and modern cloud-native capabilities.

## Anti-patterns
- **Overcomplicating Sidecars**: Avoid creating complex or overly feature-rich sidecars that don't provide real value, leading to unnecessary complexity and potential failures.

## Code Examples
```python
# Example code for deploying a topz container alongside an application

# Application container
$ docker run -d <my-app-image> \
    <my-app-image>
    
# Sidecar container (topz)
$ docker run --pid=container: ${APP_ID} \
    -p 8080:8080 \
    brendanburns/topz:db0fa58 \
    /server --addr=0.0.0.0:8080
```

This demonstrates how a sidecar can be deployed alongside an application to provide introspection capabilities.

## Reference Tables

| Parameter        | Description                          |
|------------------|---------------------------------------|
| APP_ID            | Identifier for the application container |
| PROXY_PORT         | Port used by the sidecar to proxy traffic  |
| CERTIFICATE_PATH  | Path to the SSL certificate file       |

## Key Takeaways
1. Use the sidecar pattern when you need to extend legacy applications without major changes.
2. Parameterize your containers for flexibility and reusability across different use cases.
3. Always design sidecars with a stable API to ensure compatibility and avoid breaking existing functionality.

## Connects To
- [Chapter 4: Modular Application Containers](#)
- [Chapter 6: Dynamic Configuration Management](#)