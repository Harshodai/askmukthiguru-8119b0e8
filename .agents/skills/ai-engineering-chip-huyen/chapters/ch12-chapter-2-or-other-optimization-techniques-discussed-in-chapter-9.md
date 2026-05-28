# Chapter 12: Evaluate AI Systems

## Core Idea
The chapter emphasizes balancing performance metrics like latency, cost, and model quality when selecting AI models for applications.

## Frameworks Introduced
- **Model Selection Workflow**: A four-step process to evaluate models based on hard and soft attributes:
  - Filter out models with incompatible hard attributes.
  - Narrow down promising models using public benchmarks.
  - Experiment with models in-house.
  - Continuously monitor models in production.

## Key Concepts
- **Hard Attributes**: Constraints like licensing, privacy, or hardware requirements that cannot be changed.
- **Soft Attributes**: Metrics like accuracy or factual consistency that can be improved.
- **Model Selection Criteria**: Includes benchmarks for cost per token, latency, and overall model quality.
- **Evaluation Pipeline**: A process to test models in-house before deployment.

## Mental Models
- Use large models when you have the infrastructure (e.g., GPUs with ample memory) and prioritize performance over cost.
- Think of latency as a soft attribute if you can optimize the model locally but a hard attribute if hosted externally.

## Anti-patterns
- **Avoiding Fixed-Priced Models**: Using commercial APIs without considering scalability or cost optimization.
- **Ignoring Privacy Constraints**: Hosting models that require sensitive data without proper policies.

## Code Examples
```python
# Example code to evaluate models based on latency and cost
def evaluate_model(model_name, latency, cost_per_token):
    if latency < 200ms and cost_per_token < $30M:
        return "Ideal"
    elif latency < 100ms and cost_per_token < $15M:
        return "Optimized"
    else:
        return "Consider Alternative"
```

## Reference Tables
| Metric               | Benchmark       | Hard Requirement | Ideal |
|----------------------|-----------------|------------------|-------|
| Cost per token       | <$30/Million   | Fixed pricing    | <$15M/ Million |
| Latency (P90)        | <200ms          | <100ms           | <100ms |

## Key Takeaways
1. Prioritize models that balance cost and performance based on your application's needs.
2. Evaluate both hard and soft attributes when selecting a model.
3. Optimize for latency if you can host the model locally; consider APIs otherwise.

## Connects To
- Relates to chapters on training data policies (Chapter 1) and optimization techniques (Chapter 9).