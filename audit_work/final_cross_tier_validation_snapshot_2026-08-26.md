# Final validation snapshot — 2026-08-26

- Backend: 2463 passed, 30 skipped, 1 warning
- Focused suites: 52 passed
- Distress repeated: n=20, backend p50/p95 12.0/16.55 ms, wall p50/p95 276.81/289.67 ms
- Final greeting proof: n=1, backend 5 ms, wall 391.14 ms, route instant_greeting, provider none
- Runtime: Docker Running=true, health=healthy, API ready=false because okf_compiled is missing
- Repository: no commit or push performed

## Git status

 [31mM[m .env.example
 [31mM[m CLAUDE.md
 [31mM[m README.md
 [31mM[m backend/app/config.py
 [31mM[m backend/app/context.py
 [31mM[m backend/app/orchestrator.py
 [31mM[m backend/app/orchestrator_utils.py
 [31mM[m backend/app/pipeline/pipeline_coordinator.py
 [31mM[m backend/app/pipeline/result.py
 [31mM[m backend/app/pipeline/stages/cache_stage.py
 [31mM[m backend/app/pipeline/stages/context.py
 [31mM[m backend/app/pipeline/stages/glue_stages.py
 [31mM[m backend/app/pipeline/stages/graph_stage.py
 [31mM[m backend/app/pipeline/stages/guardrail_stage.py
 [31mM[m backend/app/pipeline/stages/stage_runner.py
 [31mM[m backend/app/services/job_queue.py
 [31mM[m backend/docker-compose.yml
 [31mM[m backend/rag/nodes/intent.py
 [31mM[m backend/rag/nodes/retrieval.py
 [31mM[m backend/rag/nodes/utils.py
 [31mM[m backend/services/openrouter_service.py
 [31mM[m backend/tests/test_job_queue.py
 [31mM[m backend/tests/test_pipeline_stages.py
 [31mM[m backend/tests/test_tiered_routing_streaming.py
 [31mM[m docs/PRODUCT_OPPORTUNITIES.md
 [31mM[m lessons.md
[31m??[m audit_work/advanced_methods_research.md
[31m??[m audit_work/compare_latency_runs.py
[31m??[m audit_work/cross_tier_latency_final_report_2026-08-26.md
[31m??[m audit_work/cross_tier_latency_summary.tsv
[31m??[m audit_work/cross_tier_log_correlation_latest.txt
[31m??[m audit_work/cross_tier_parameter_inventory_2026-08-26.md
[31m??[m audit_work/final_advanced_methods_snapshot.txt
[31m??[m audit_work/final_cross_tier_validation_snapshot_2026-08-26.md
[31m??[m audit_work/final_validation_snapshot.txt
[31m??[m audit_work/github_latency_gems.err
[31m??[m audit_work/github_latency_gems.jsonl
[31m??[m audit_work/latency_baseline_latest.txt
[31m??[m audit_work/latency_benchmark_distress_20.jsonl
[31m??[m audit_work/latency_benchmark_distress_20_summary.json
[31m??[m audit_work/latency_benchmark_repeated.py
[31m??[m audit_work/latency_budget.py
[31m??[m audit_work/latency_budget_current.tsv
[31m??[m audit_work/latency_budget_latest.tsv
[31m??[m audit_work/latency_experiment_comparison.md
[31m??[m audit_work/latency_fast_casual_after.jsonl
[31m??[m audit_work/latency_fast_casual_after_summary.json
[31m??[m audit_work/latency_fast_casual_cache_bypass_final.jsonl
[31m??[m audit_work/latency_fast_casual_cache_bypass_final_summary.json
[31m??[m audit_work/latency_fast_casual_final.jsonl
[31m??[m audit_work/latency_fast_casual_final_summary.json
[31m??[m audit_work/latency_fast_casual_narrowed_final.jsonl
[31m??[m audit_work/latency_fast_casual_narrowed_final_summary.json
[31m??[m audit_work/latency_fast_casual_postrestart.jsonl
[31m??[m audit_work/latency_fast_casual_postrestart_summary.json
[31m??[m audit_work/latency_fast_casual_shared_final.jsonl
[31m??[m audit_work/latency_fast_casual_shared_final_summary.json
[31m??[m audit_work/latency_final_report.md
[31m??[m audit_work/latency_log_correlations.txt
[31m??[m audit_work/latency_log_correlations_current.txt
[31m??[m audit_work/latency_postchange_allroutes.jsonl
[31m??[m audit_work/latency_postchange_allroutes_summary.json
[31m??[m audit_work/latency_postselection_allroutes.jsonl
[31m??[m audit_work/latency_postselection_allroutes_summary.json
[31m??[m audit_work/latency_probe.py
[31m??[m audit_work/latency_probe_all_routes.jsonl
[31m??[m audit_work/latency_probe_all_routes.py
[31m??[m audit_work/latency_probe_cross_tier_anchor.jsonl
[31m??[m audit_work/latency_probe_current.jsonl
[31m??[m audit_work/latency_probe_hindi.py
[31m??[m audit_work/latency_probe_hindi_final.jsonl
[31m??[m audit_work/latency_probe_latest.jsonl
[31m??[m audit_work/latency_probe_no_hyde.jsonl
[31m??[m audit_work/latency_probe_no_hyde_genuine.jsonl
[31m??[m audit_work/latency_probe_no_hyde_uncached.jsonl
[31m??[m audit_work/latency_probe_no_hyde_uncached2.jsonl
[31m??[m audit_work/latency_probe_treatment_final.jsonl
[31m??[m audit_work/latency_research.md
[31m??[m audit_work/recommendation_reconciliation.md
[31m??[m audit_work/ruthless_research_dossier_2026-08-26.md
[31m??[m audit_work/ruthless_web_research_2026-08-26.md
[31m??[m audit_work/summarize_cross_tier.py
[31m??[m backend/app/latency_catalog.py
[31m??[m backend/app/routing_primitives.py
[31m??[m backend/tests/test_greeting_short_circuit.py
[31m??[m backend/tests/test_latency_catalog.py

## Diff stat

 .env.example                                   |   7 [32m++[m
 CLAUDE.md                                      |   6 [32m+[m[31m-[m
 README.md                                      |   4 [32m+[m
 backend/app/config.py                          |   8 [32m++[m
 backend/app/context.py                         |   2 [32m+[m
 backend/app/orchestrator.py                    |  48 [32m++++++++[m[31m-[m
 backend/app/orchestrator_utils.py              |  38 [32m++++[m[31m---[m
 backend/app/pipeline/pipeline_coordinator.py   | 131 [32m++++++++++++++++++++++[m[31m---[m
 backend/app/pipeline/result.py                 |   3 [32m+[m
 backend/app/pipeline/stages/cache_stage.py     |  68 [32m+++++++++++[m[31m--[m
 backend/app/pipeline/stages/context.py         |  11 [32m++[m[31m-[m
 backend/app/pipeline/stages/glue_stages.py     |  32 [32m++++[m[31m--[m
 backend/app/pipeline/stages/graph_stage.py     |  37 [32m++++++[m[31m-[m
 backend/app/pipeline/stages/guardrail_stage.py |   4 [32m+[m[31m-[m
 backend/app/pipeline/stages/stage_runner.py    |  30 [32m+++++[m[31m-[m
 backend/app/services/job_queue.py              |  37 [32m++++++[m[31m-[m
 backend/docker-compose.yml                     |   9 [32m++[m
 backend/rag/nodes/intent.py                    |  13 [32m++[m[31m-[m
 backend/rag/nodes/retrieval.py                 |   7 [32m+[m[31m-[m
 backend/rag/nodes/utils.py                     |  26 [32m+++++[m
 backend/services/openrouter_service.py         |  78 [32m++++++++++++++[m[31m-[m
 backend/tests/test_job_queue.py                |  84 [32m++++++++++++++++[m
 backend/tests/test_pipeline_stages.py          |  57 [32m+++++++++++[m
 backend/tests/test_tiered_routing_streaming.py |  53 [32m++++++++++[m
 docs/PRODUCT_OPPORTUNITIES.md                  |   1 [32m+[m
 lessons.md                                     |  47 [32m+++++++++[m
 26 files changed, 777 insertions(+), 64 deletions(-)
