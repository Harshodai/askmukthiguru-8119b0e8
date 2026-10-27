# Chapter 14: Chapter 11

## Core Idea
Work queues are a batch processing pattern that enables efficient parallel execution of independent tasks by leveraging reusable container interfaces for source and worker functionality.

## Frameworks Introduced
- **Source Container Interface**: Manages retrieval of work items from an external source.
  - When to use: When you need a shared interface to fetch work items from an external source like a REST API or file system.
  - How: Implements HTTP/REST APIs with GET requests for item retrieval and versioning.

- **Worker Container Interface**: Defines the entry point for processing individual work items.
  - When to use: When tasks are independent and can be processed in parallel without shared state.
  - How: Implements a single API endpoint that handles task execution, often using file-based persistent storage for data persistence.

- **Work Queue Algorithm**: Manages the lifecycle of work items from source to completion.
  - When to use: For batch processing systems where tasks are added dynamically and processed in parallel.
  - How: Uses Kubernetes Job objects to schedule and manage worker containers, ensuring reliable execution even with failures.

## Key Concepts
- **Work Queue**: A container-based system for managing batches of independent tasks.
- **Source Container**: Manages incoming work items via HTTP/REST APIs.
- **Worker Container**: Executes individual tasks using persistent storage (e.g., file-based).
- **Dynamic Scaling**: Adjusts parallelism based on workload demands, implemented with autoscalers like KEDA.

## Mental Models
- Use source containers when you need a shared interface to fetch work items from an external source.
  - Think of source containers as the entry point for your work queue's task delivery mechanism.

- Use worker containers when tasks are independent and can be processed in parallel without shared state.
  - Think of worker containers as the execution engines that process individual tasks, often using file-based storage to persist data between executions.

## Anti-patterns
- **Bursty Workloads Without Autoscaling**: Failing to scale resources during periods of high demand leads to system instability or increased latency.
  - What to avoid: Processing a large batch of work items without autoscaling resources, leading to overwhelmed workers and degraded performance.

## Code Examples
```python
# Example Python script for implementing a work queue using Kubernetes and Docker

import requests
from kubernetes import client, config
import time

namespace = "default"

def make_container(item, obj):
    container = client.V1Container()
    container.image = "my/worker-image"
    container.name = "worker"
    return container

def make_job(item):
    response = requests.get(f"http://localhost/api/v1/items/{item}")
    obj = json.loads(response.text)
    
    job = client.V1Job()
    job.metadata = client.V1ObjectMetadata()
    job.metadata.name = item
    job.spec = client.V1JobSpec()
    job.spec.template = client.V1PodTemplate()
    job.spec.template.spec = client.V1PodTemplateSpec()
    job.spec.template.spec.restart_policy = "Never"
    
    job.spec.template.spec.containers = [
        make_container(item, obj)
    ]
    
    return job

def update_queue(batch):
    response = requests.get("http://localhost/api/v1/items")
    items = response.json()["items"]
    ret = batch.list_namespaced_job(namespace, watch=False)
    
    for item in items:
        found = False
        for i in ret.items:
            if i.metadata.name == item:
                found = True
                break
        if not found:
            job = make_job(item)
            batch.create_namespaced_job(namespace, job)
            
config.load_kube_config()
batch = client.BatchV1Api()
while True:
    update_queue(batch)
    time.sleep(10)
```

- **What it demonstrates**: A work queue implementation using Kubernetes and Docker containers to manage task processing in a scalable manner.

## Reference Tables
| Framework                | Description                                                                 |
|-------------------------|-----------------------------------------------------------------------------|
| Source Container Interface | Manages retrieval of work items from an external source via HTTP/REST APIs.  |
| Worker Container Interface  | Defines the API for processing individual work items using persistent storage. |
| Work Queue Algorithm      | Manages lifecycle of tasks, ensuring reliable execution with autoscaling support. |

## Key Takeaways
1. Use reusable source and worker container interfaces to implement a batch processing system.
2. Leverage dynamic scaling techniques like KEDA to handle varying workloads efficiently.
3. Utilize the multiworker pattern for code reuse across different tasks.

## Connects To
- **Containerization**: Relates to the use of containers in implementing source and worker interfaces (e.g., Docker, Kubernetes).
- **Orchestrators**: Connects with Kubernetes for task scheduling and resource management.
- **Dynamic Scaling**: Relates to autoscaling strategies like KEDA for handling workload fluctuations.