# Hindi repeat timing evidence — 2026-08-22

Five sequential requests used the same anonymous session against the live Railway backend after the targeted query-cache flush. All five returned HTTP 200, `grounding_state=grounded`, faithfulness `0.8`, and response lengths from 208 to 442 characters.

| Run | Wall ms | Internal latency ms | Intent router ms | Retrieval ms | Generation ms |
|---:|---:|---:|---:|---:|---:|
| 1 | 5,183 | 4,266 | 311.9 | 747.1 | 1,971.0 |
| 2 | 3,886 | 2,961 | 302.7 | 525.3 | 1,091.5 |
| 3 | 4,187 | 3,263 | 297.4 | 463.8 | 1,438.3 |
| 4 | 3,754 | 3,012 | 308.8 | 506.0 | 1,114.7 |
| 5 | 4,073 | 3,233 | 293.0 | 482.0 | 1,389.8 |

The current same-session warm control is materially better than the earlier 17–19 second tail, but it does not prove that the tail is eliminated. It shows the dominant measured stages in this sample are generation and retrieval, with an internal-to-wall gap of approximately 0.8–0.9 seconds. The next gate is to correlate slow HTTP request IDs with provider/retrieval logs and run a larger, bounded held-out matrix; no provider, reranker, embedding, graph, or fusion setting was changed based on this sample.
