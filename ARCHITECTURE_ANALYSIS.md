# Architecture Analysis: RAG Pipeline Layers

## Current State

### Documentation Claims (ARCHITECTURE.md)
- Layer 1: NeMo Input Rail (guardrails/rails.py)
- Layer 2: Depression Detector (depression_detector.py)
- Layers 3-11: LangGraph Pipeline (rag/graph.py) - **9 layers**
- Layer 12: NeMo Output Rail

### Actual Implementation Count
From `backend/rag/graph.py` node registrations:
1. intent_router
2. resolve_followup
3. decompose_query
4. navigate_knowledge_tree
5. retrieve_documents
6. rerank_documents
7. grade_documents
8. enrich_context
9. check_context_sufficiency
10. rewrite_query
11. generate_answer
12. reflect_on_answer
13. verify_answer
14. explain_retrieval
15. context_engineer
16. format_final_answer
17. check_contradiction
18. handle_casual
19. handle_distress
20. handle_meditation
21. handle_fallback
22. generate_hyde

**Total: 22 nodes in the LangGraph pipeline**

### Execution Flow Analysis
From the graph implementation, the actual execution paths are:

**QUERY Path (most complex):**
1. intent_router
2. resolve_followup
3. decompose_query
4. navigate_knowledge_tree (parallel)
5. generate_hyde (parallel)
6. retrieve_documents
7. rerank_documents
8. grade_documents
9. check_context_sufficiency
10. [IF relevant] enrich_context
11. [IF relevant] context_engineer
12. [IF relevant] generate_answer
13. [IF relevant] reflect_on_answer
14. [IF needs_correction AND rewrite_count < 3] rewrite_query (loop back to 6)
15. [IF needs_correction AND rewrite_count >= 3] handle_fallback
16. [IF verified] check_contradiction
17. [IF verified] explain_retrieval (parallel)
18. [IF verified] format_final_answer
19. END

**Simplified Count (excluding parallel paths and conditionals):**
- Core sequential path: ~12-15 nodes depending on conditions
- But documentation claims only layers 3-11 (9 layers) are in the graph

## Discrepancy
The documentation states "Layers 3-11: LangGraph Pipeline" implying 9 layers, but the actual implementation has significantly more nodes (22 total registered nodes).

## Options for Unit 3
1. **Implement missing layers with real logic**: Actually, all the layers seem to be implemented already - the issue might be that some are not fully fleshed out or documented properly.

2. **Update documentation to match actual implementation**: Update ARCHITECTURE.md to accurately reflect the actual number and function of layers in the LangGraph pipeline.

## Recommendation
Given that the CLAUDE.md file already has a detailed and accurate description of the pipeline (~20 specialized nodes), the issue is likely that ARCHITECTURE.md needs to be updated to match the actual implementation rather than the other way around.

Let me check if any of the nodes are stubs or missing real implementation...