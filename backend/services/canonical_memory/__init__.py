"""Canonical memory extraction pipeline — Phases 3, 5, 6, 9, 10, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25 of Adaptive Memory System.

This package provides isolated, stateless extraction of MemoryCandidate[] from
bounded conversation windows. The extractor MUST NOT write directly to any store.

Phase 5 adds the MemoryResolver: applies judge decisions (CREATE, UPDATE, MERGE,
IGNORE, EXPIRE, DELETE, ESCALATE) to the canonical Postgres store with idempotency,
optimistic concurrency, and audit trail.

Phase 6 adds the CanonicalMemoryConsolidator: threshold-triggered consolidation
that reduces redundancy without information loss. Uses snapshot → consolidate →
validate → commit safety pattern with rollback capability.

Phase 9 adds history_separator: strict boundary enforcement between History,
Memory, and Knowledge layers, ensuring transient conversation info never becomes
durable memory unintentionally.

Phase 10 adds context_builder: adaptive context orchestration that dynamically
allocates token budget across Memory, History, and Knowledge layers based on
query intent. Fixed 30/30/40 splits are replaced with intent-driven allocation.
Memory is invisible when irrelevant. Provenance labels and injection fences
are applied to all context blocks.

Phase 16 adds evaluation: harness for memory health, retrieval quality, and
full evaluation suites. MemoryEvaluator provides golden dataset evaluation,
blind comparison support, and scoring across health, deduplication, freshness,
and retrieval dimensions.

Phase 17 adds simulation: longitudinal scenario-based testing of memory
quality over time. MemorySimulator runs deterministic conversation sequences
and measures deduplication, contradiction resolution, deletion propagation,
and consistency scoring across multi-turn interactions.

Phase 18 adds cost_tracker: budget-aware cost tracking across LLM calls,
vector operations, DB operations, consolidation, and retrieval. Provides
windowed cost accounting, budget enforcement, and consolidation cost estimation.

Phase 19 adds performance: latency monitoring, percentile analysis, budget
enforcement, stress testing, and query benchmarking for the memory system.
PerformanceMonitor tracks operation latencies against configurable budgets
and provides summary statistics for capacity planning.

Phase 20 adds resilience: circuit breaker pattern for fault isolation,
graceful degradation with automatic fallback, and chaos test runner
for resilience verification across failure modes (DB timeout, vector
unavailable, partial failure, slow response, LLM unavailable).

Usage:
    from services.canonical_memory.extractor import extract_memory_candidates
    result = await extract_memory_candidates(turns, user_id="...", language_hint="en")

    from services.canonical_memory.resolver import MemoryResolver, create_resolver
    resolver = create_resolver(supabase_client)
    resolution = await resolver.resolve(judge_decision, user_id="...")

    from services.canonical_memory.consolidator import create_consolidator
    consolidator = create_consolidator(supabase_client, llm_service)
    if await consolidator.should_consolidate(user_id):
        result = await consolidator.consolidate(user_id)

    from services.canonical_memory.history_separator import (
        classify_conversation_turn,
        build_history_context,
        validate_separation,
    )
    classification = classify_conversation_turn(user_msg, asst_resp)
    history_ctx = build_history_context(session_messages, max_tokens=1024)
    is_valid = validate_separation(memory_context, history_context)

    from services.canonical_memory.context_builder import (
        create_orchestrator,
        classify_query_intent,
        QueryIntent,
    )
    orchestrator = create_orchestrator(memory_retriever, knowledge_retriever)
    context = await orchestrator.build_context(user_id, query, session_messages)
    prompt_section = context.to_prompt_section()

    from services.canonical_memory.observability import (
        MemoryMetrics,
        MemoryMonitor,
        get_monitor,
    )
    monitor = get_monitor()
    monitor.record("extraction_started", {"user_id": user_id})
    health = monitor.get_health()

    from services.canonical_memory.evaluation import (
        MemoryEvaluator,
        EvalResult,
        EvalSuite,
        EvalVerdict,
    )
    evaluator = MemoryEvaluator(db_client, retriever=retriever)
    health_suite = evaluator.evaluate_memory_health(user_id)
    full_report = evaluator.run_full_eval(user_id, queries=[...])

    from services.canonical_memory.simulation import (
        MemorySimulator,
        SimulationScenario,
        SimulatedTurn,
    )
    sim = MemorySimulator(db_client=db)
    scenario = sim.create_repeated_info_scenario(user_id)
    result = sim.run_scenario(scenario)
    summary = sim.generate_summary([result])
"""

from services.canonical_memory.models import ExtractionResult, MemoryCandidate, MemoryType
from services.canonical_memory.extractor import extract_memory_candidates
from services.canonical_memory.resolver import MemoryResolver, ResolutionResult, create_resolver
from services.canonical_memory.consolidator import (
    CanonicalMemoryConsolidator,
    ConsolidationCandidate,
    ConsolidationResult,
    create_consolidator,
)
from services.canonical_memory.history_separator import (
    TurnClassification,
    classify_conversation_turn,
    is_transient,
    build_history_context,
    validate_separation,
)
from services.canonical_memory.context_builder import (
    AdaptiveContextOrchestrator,
    BudgetAllocation,
    ContextResult,
    LayerBlock,
    QueryIntent,
    allocate_budget,
    classify_query_intent,
    create_orchestrator,
)
from services.canonical_memory.security import (
    check_injection_attempt,
    sanitize_memory_for_context,
    validate_deletion_completeness,
    validate_user_scoped_query,
)
from services.canonical_memory.privacy import (
    ConsentScope,
    MemoryPrivacyManager,
)
from services.canonical_memory.observability import (
    MemoryMetrics,
    MemoryMonitor,
    get_monitor,
)
from services.canonical_memory.evaluation import (
    EvalResult,
    EvalSuite,
    EvalVerdict,
    MemoryEvaluator,
)
from services.canonical_memory.simulation import (
    MemorySimulator,
    SimulationResult,
    SimulationScenario,
    SimulatedTurn,
    TurnResult,
)
from services.canonical_memory.cost_tracker import (
    CostCategory,
    CostEntry,
    CostTracker,
    estimate_consolidation_cost,
)
from services.canonical_memory.performance import (
    LatencyRecord,
    PerformanceMonitor,
    benchmark_query_latency,
)
from services.canonical_memory.resilience import (
    CircuitBreaker,
    CircuitState,
    ChaosScenario,
    ChaosTestRunner,
    FailureMode,
    GracefulDegradation,
    get_circuit_breaker,
    get_graceful_degradation,
)
from services.canonical_memory.self_healing import (
    DriftDetector,
    RepairAction,
    RepairOutcome,
    RepairRecord,
    SelfHealer,
    get_self_healer,
)
from services.canonical_memory.migration import (
    LegacyTable,
    MigrationManager,
    MigrationPhase,
    MigrationProgress,
    get_migration_manager,
)
from services.canonical_memory.shadow import (
    ShadowMode,
    ShadowResult,
    get_shadow_mode,
)
from services.canonical_memory.canary import (
    CanaryConfig,
    CanaryDeployment,
    CanaryStage,
    get_canary_deployment,
)
from services.canonical_memory.red_team import (
    AttackCategory,
    AttackLibrary,
    AttackResult,
    AttackVector,
    RedTeamTestRunner,
    get_red_team_runner,
)

__all__ = [
    "MemoryType",
    "MemoryCandidate",
    "ExtractionResult",
    "extract_memory_candidates",
    "MemoryResolver",
    "ResolutionResult",
    "create_resolver",
    "CanonicalMemoryConsolidator",
    "ConsolidationCandidate",
    "ConsolidationResult",
    "create_consolidator",
    "TurnClassification",
    "classify_conversation_turn",
    "is_transient",
    "build_history_context",
    "validate_separation",
    "AdaptiveContextOrchestrator",
    "BudgetAllocation",
    "ContextResult",
    "LayerBlock",
    "QueryIntent",
    "allocate_budget",
    "classify_query_intent",
    "create_orchestrator",
    "check_injection_attempt",
    "sanitize_memory_for_context",
    "validate_deletion_completeness",
    "validate_user_scoped_query",
    "ConsentScope",
    "MemoryPrivacyManager",
    "MemoryMetrics",
    "MemoryMonitor",
    "get_monitor",
    "EvalResult",
    "EvalSuite",
    "EvalVerdict",
    "MemoryEvaluator",
    "MemorySimulator",
    "SimulationResult",
    "SimulationScenario",
    "SimulatedTurn",
    "TurnResult",
    "CostCategory",
    "CostEntry",
    "CostTracker",
    "estimate_consolidation_cost",
    "LatencyRecord",
    "PerformanceMonitor",
    "benchmark_query_latency",
    "CircuitBreaker",
    "CircuitState",
    "ChaosScenario",
    "ChaosTestRunner",
    "FailureMode",
    "GracefulDegradation",
    "get_circuit_breaker",
    "get_graceful_degradation",
    "DriftDetector",
    "RepairAction",
    "RepairOutcome",
    "RepairRecord",
    "SelfHealer",
    "get_self_healer",
    "LegacyTable",
    "MigrationManager",
    "MigrationPhase",
    "MigrationProgress",
    "get_migration_manager",
    "ShadowMode",
    "ShadowResult",
    "get_shadow_mode",
    "CanaryConfig",
    "CanaryDeployment",
    "CanaryStage",
    "get_canary_deployment",
    "AttackCategory",
    "AttackLibrary",
    "AttackResult",
    "AttackVector",
    "RedTeamTestRunner",
    "get_red_team_runner",
]
