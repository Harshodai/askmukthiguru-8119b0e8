# Chapter 21: 308 APPENDIX B Python Development Environment

## Core Idea
This chapter teaches readers how to efficiently manage Python dependencies by creating isolated virtual environments using VS Code and Dev Containers (Docker), ensuring project consistency and avoiding conflicts between packages.

## Frameworks Introduced
- **Venv**: 
  - When to use: For managing Python packages in isolated environments.
  - How: Create a new Venv via the command panel, select requirements.txt, and install dependencies within the environment.

- **Docker**:
  - When to use: For containerizing code execution, especially for advanced agents or frameworks that require isolation.
  - How: Install Docker Desktop, configure VS Code extensions, and start containers from folders or directly in VS Code.

## Key Concepts
- **requirements.txt**: A file listing all dependencies needed for a project, ensuring consistent installations across environments.
- **Isolated Containers**: Virtualized environments that prevent operating system interference and provide a controlled base for application deployment.

## Mental Models
- Use Venv when you need to manage Python packages in isolated environments. Think of Venv as an essential tool for dependency control.

## Anti-patterns
- Avoid not creating or misconfiguring virtual environments, as this can lead to package conflicts and inconsistent project setups.

## Code Examples
```python
# Example Venv setup
import subprocess

def create_venv():
    subprocess.run(['python', '-m', 'venv', 'myenv'], shell=True)
    subprocess.run(['source', 'myenv/bin/activate'], shell=True)
    print("Virtual environment created successfully.")

create_venv()
```
This demonstrates creating a Venv and activating it, ensuring dependencies are isolated.

```bash
# Example Docker setup
docker-compose down && docker-compose up --build
```
This shows how to start a container from a folder using Docker in VS Code for executing code in isolation.

## Reference Tables

| Use Case                | Framework       |
|-------------------------|-----------------|
| Development with multiple packages | Venv             |
| Containerized execution  | Docker          |

## Key Takeaways
1. Create isolated virtual environments to manage Python dependencies effectively.
2. Use `requirements.txt` to ensure consistent installations across environments.
3. Prefer Venv for development and Docker for containerized advanced tasks.

## Connects To
- Chapters on dependency management (Chapter X)
- Concepts related to containerization (Chapter Y)