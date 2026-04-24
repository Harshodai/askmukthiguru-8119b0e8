# Deep research — concept references

Annotated references for every technique used in this dashboard.

## RAGAS — four metrics

- **Faithfulness** — fraction of answer claims supported by retrieved context. Ranges 0–1.
- **Answer relevancy** — how well the answer addresses the question (mean cosine of LLM-generated questions back to the original).
- **Context precision** — fraction of retrieved chunks that are relevant.
- **Context recall** — fraction of ground-truth facts covered by retrieved chunks (requires reference answer).

References:
- RAGAS paper: https://arxiv.org/abs/2309.15217
- RAGAS docs: https://docs.ragas.io/
- LLM-as-judge survey: https://arxiv.org/abs/2306.05685

## CRAG — Corrective RAG
Grade retrieved chunks; rewrite query and re-retrieve up to N times if poor.
Paper: https://arxiv.org/abs/2401.15884

## Self-RAG
LLM critiques its own answer for faithfulness to retrieved context.
Paper: https://arxiv.org/abs/2310.11511

## CoVe — Chain of Verification
Generate sub-questions to fact-check the answer before returning.
Paper: https://arxiv.org/abs/2309.11495

## Stimulus RAG
Extract key hint phrases from retrieved docs before generation to focus the LLM.
Paper: https://arxiv.org/abs/2305.03268

## Tracing
Our `trace_spans` table is **OTel-inspired** (parent_span_id, name, start_ms, duration_ms, attributes) — not OTel-protocol-compliant. Use it for waterfall UI; export to OTel collector later if desired.
- OTel data model: https://opentelemetry.io/docs/specs/otel/trace/api/
- LLM tracing patterns: https://www.langchain.com/langsmith

## Hallucination detection (LLM-as-judge)
Single-call multi-metric judging via tool/function calling is the cheapest reliable pattern for production.
- LLM-as-judge survey: https://arxiv.org/abs/2306.05685
- Tool-calling reliability: https://platform.openai.com/docs/guides/function-calling

## Prompt injection
Detection patterns: instruction-override regex pre-pass + LLM judge with examples.
- OWASP LLM01: https://owasp.org/www-project-top-10-for-large-language-model-applications/
- Anthropic safety guide: https://docs.anthropic.com/claude/docs/use-xml-tags

## Golden-dataset regression
Treat eval runs like CI: fail PRs if `avg_faithfulness` drops > 2pp.
- Anthropic evals cookbook: https://docs.anthropic.com/claude/docs/building-evals

## Semantic clustering
K-means over response embeddings produces topic clusters. Upgrade to HDBSCAN if topics are noisy.
- pgvector: https://github.com/pgvector/pgvector

## Supabase RLS + security-definer
Storing roles on `profiles` enables privilege escalation if RLS is misconfigured. The `user_roles` + `has_role()` pattern with `SECURITY DEFINER` avoids this and prevents RLS recursion.
- Supabase RLS: https://supabase.com/docs/guides/auth/row-level-security
- Custom claims: https://supabase.com/docs/guides/auth/auth-hooks
