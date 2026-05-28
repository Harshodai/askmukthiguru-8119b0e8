# Chapter 13: Monitoring in Production

## Core Idea
Monitoring is essential for maintaining reliable agent systems; it combines infrastructure, tools, and visualization to ensure agents operate optimally and adapt to changes.

## Frameworks Introduced
- **OpenTelemetry (OT)**: Collects spans and metrics from distributed applications.
  - When to use: Instrumentation for real-time monitoring of agent workflows.
  - How: Tracks tool calls, plan executions, and outputs for visualization tools.
  
- **Loki**: A logging framework for structured logs with indexing capabilities.
  - When to use: For detailed trace analysis in agent monitoring.
  - How: Builds hierarchical log structures for efficient querying.

- **Tempo**: A tracing library optimized for foundation models.
  - When to use: Instrumenting agent execution graphs and traces.
  - How: Provides granular tracing data for debugging and observability.

Grafana: A visualization platform that integrates with OT, Loki, and Tempo.
- When to use: For creating dashboards and alerting systems.
- How: Aggregates monitoring data into a single interface for insights.

## Key Concepts
- **Monitoring**: Combines infrastructure (logging, tracing) and visualization to provide real-time insights.
- **Drift Detection**: Uses KS divergence and PSI metrics to detect changes in agent behavior or inputs.
- **Fallback Logging**: Captures degraded traces for post-mortem analysis of regressions.

## Mental Models
- Use OT with Loki and Tempo when monitoring distributed agent workflows.
  - This combination provides comprehensive traceability and detailed analytics.
- Use Grafana as the visualization layer to present monitoring data in an intuitive interface.
  - This ensures teams can quickly identify issues and act on them.

## Anti-patterns
- Avoid disjointed monitoring stacks that lack integration, leading to missed insights or overlooked issues.
  - This occurs when different tools (e.g., OT, Loki, Grafana) are used separately without a unified approach.

## Code Examples
```
# Example of potential code using OpenTelemetry and Loki
from otelemetry  import Trace
from Loki  import Tempore

traced = Tempore()
tracer = traced tracer.add_as_current_span("GET /api")
tracer.add_source("http", "GET request")

@traced
async def fetch_tool():
    with tracer.start_as_current_span("HTTP GET request to tool"):
        response = await fetch_tool_url("context")
        return {"status": "success", "result": parse_response(response)}

# Example Loki query for agent metrics
lqi = Loki.query("k8s.io/agents/last-1m")
lqi.get("api/latency")
```

## Reference Tables
### Metric Comparison Table
| Metric                | Example Values |
|-----------------------|---------------|
| Request Latency        | 200ms         |
| Query Time           | 500ms         |

### Distribution Shift Detection Methods
| Method                  | Use Case                          |
|------------------------|------------------------------------|
| Kolmogorov-Smirnov (KS) | Detecting distribution drift in query patterns. |
| Population Stability Index (PSI) | Identifying categorical changes in tool usage. |

## Key Takeaways
1. Use shadow mode to debug agent workflows while maintaining production.
2. Implement canary deployments for gradual rollouts and early detection of regressions.
3. Leverage user feedback analytics alongside automated evaluation signals.
4. Monitor distribution drift using KS divergence and PSI metrics.

## Connects To
- Chapter 9: Infrastructure
- Chapter 10: Building Agent Workflow
- Chapter 11: Extending the Foundation Model