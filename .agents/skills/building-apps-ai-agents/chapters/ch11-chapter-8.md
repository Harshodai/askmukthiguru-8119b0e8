# Chapter 11: Multiagent Systems

## Core Idea
Multiagent systems are essential for handling complex tasks that require collaboration among multiple intelligent agents, enabling scalability, adaptability, and efficiency in real-world applications.

## Frameworks Introduced
- **Orchestrator**: Manages workflows by sequencing tasks across agents, ensuring coordination and failure recovery. Best used when tasks have clear dependencies.
  - When to use: For complex, sequential workflows with potential task failures.
  - How: Orchestrators define task sequences, handle retries, and manage state persistence.

- **Ray (Ray Framework)**: A distributed actor framework for Python that supports stateful agents in a flexible, scalable environment. Ideal for Python-based applications requiring high concurrency and fault tolerance.
  - When to use: For Python applications needing async/await patterns and resuming failed tasks.

- **Orleans (Orleans Framework)**: A virtual actor model for Java-based multiagent systems, offering lightweight state management and cross-platform compatibility. Suitable for enterprise-level applications.
  - When to use: For Java-based distributed systems requiring lightweight actor models.

## Key Concepts
- **State Management**: Agents maintain internal state to track progress and handle failures. Ray uses Redis for in-memory state, while Orleans relies on external storage like JSONL.
- **Communication Methods**: Message brokers (Kafka, Redis) enable async communication without direct connections. Actors use RESTful APIs or gRPC for programmatic access.
- **Coordination Strategies**: Options include democratic voting, manager-based orchestration, and hierarchical coordination to balance robustness and flexibility.

## Mental Models
- **Actor Frameworks**: Treat agents as stateful objects that process tasks sequentially, with options for retries and resuming failed states.
  - Example: Ray's `SpecialPurposeLL` actor handles foundation model calls and task retries.
- **Orleans**: Virtual actors manage persistent state across instances without relying on shared memory, using Redis for async communication.

## Anti-patterns
- **Centralized Control**: Avoid monolithic systems with a single agent handling all tasks. Instead, distribute responsibilities among multiple agents.
- **Lack of Coordination**: Implement robust failure handling and retries to ensure task completion even when components fail.
- **Inadequate State Management**: Use stateful actors to track progress and handle failures gracefully.

## Code Examples
```python
# Ray Example: SpecialPurposeLL Actor
class SpecialPurposeLLActor(Actor):
    def __init__(self, name, llm, tools, system_prompt):
        self.name = name
        self.llm = llm
        self.tools = tools
        self.prompt = system_prompt

    async def process_task(self, operation, messages):
        if not operation:
            operation = {"operation_id": "UNKNOWN", 
                         "type": "task",
                         "priority": "medium"}
        
        operation_json = json.dumps(operation)
        full_prompt = f"{self.prompt}\n\n{operation_json}"
        
        # Add task to system state
        step_key = str(len(self.internal_state) + 1)
        self.internal_state[step_key] = {"status": "processing", 
                                        "timestamp": datetime.now().isoformat()}
        
        result_messages = []
        result = self.llm.invoke(full_prompt)
        
        # Handle retries based on success
        for attempt in range(3):
            if not hasattr(result, 'tool_calls'):
                break
            
            tool_calls = json.loads(result.tool_calls)
            new_result = {"task_id": operation["task_id"], 
                         "from": operation["from"],
                         "to": operation["to"], 
                         "messages": result['messages']}
            
            # Add task to system state
            step_key = str(len(self.internal_state) + 1)
            self.internal_state[step_key] = {"status": "completed",
                                        "timestamp": datetime.now().isoformat(),
                                        "result": new_result}
            
            if attempt == 2:
                return {"task_id": operation["task_id"], 
                        "from": operation["from"],
                        "to": operation["to"], 
                        "messages": result['messages']}
        
        # Update and return messages
        self._update_messages(result['messages'])
        return {"task_id": operation["task_id"], 
                "from": operation["from"],
                "to": operation["to"], 
                "messages": result['messages']}

# Orleans Example: SpecialistActor
class SpecialistActor:
    def __init__(self, name, llm, tools, prompt):
        self.name = name
        self.llm = llm
        self.tools = tools
        self.prompt = prompt
        
    def process_task(self, operation, messages):
        # Check if agent is available and has sufficient capacity
        if not hasattr(self, 'available') or \
           (datetime.now() - self.available_start) > self.service_time:
            return {"task_id": task_id, 
                    "from": from_, 
                    "to": to, 
                    "messages": messages}
        
        # Process the task and schedule for next time
        result_messages = self.process_task_internal(operation, messages)
        self._schedule_task(operation_id, operation, result_messages)

    def _schedule_task(self, operation_id, operation, result_messages):
        step_key = str(len(self.assigned_tasks) + 1)
        self.assigned_tasks[step_key] = {
            "operation_id": operation_id,
            "operation": operation,
            "messages": result_messages
        }
```

## Reference Tables

| Framework | Key Features                                      |
|----------|------------------------------------------------|
| Ray         | Stateful actors, async/await patterns, Redis state storage, Python-based |
| Orleans    | Virtual actors, lightweight storage, Redis-based communication, Java-based  |
| Akka       | Stateless HKCP-style actors, message brokers, JVM-based |

## Key Takeaways
1. Multiagent systems enable scalability and adaptability in complex tasks.
2. Choosing the right framework depends on task complexity, concurrency needs, and language preferences.
3. Proper state management and communication are critical for system reliability.
4. Orchestrators handle coordination and failure recovery across agents.

## Connects To
- State Management (Chapter 10)
- Service Composition (Chapter 9)