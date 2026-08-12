# Product Improvement Discovery — 2026-08-12

## Evidence summary

AskMukthiGuru is a source-grounded spiritual-guidance product, not a mental-health provider or a simulated human teacher. The highest-confidence product work therefore prioritises calibrated trust, crisis-safe boundaries, privacy clarity, and measurement over engagement optimisation.

| Finding | Product implication | Evidence |
|---|---|---|
| Consumer AI chat experiences should not be presented as psychotherapy or a substitute for qualified care. Developers should clearly disclose AI identity, limitations, safeguards, and data practices. | Maintain a persistent, plain-language AI/limits disclosure; route distress to supportive, non-diagnostic guidance and urgent human resources; prohibit clinical claims. | [APA advisory][1] |
| Designs that create emotional dependency or overly human-like attachment are a safety risk. Break nudges, non-exclusive language, and real-world support encouragement are recommended. | Add dependency-risk instrumentation and gentle breaks; never position the product as a person, sole guide, or replacement for relationships. | [APA advisory][1] |
| Reliable AI products require a clear stated purpose, contextual filtering, risk-tiered evaluation, robust activity monitoring, privacy transparency, testing on realistic users, and accountable governance. | Convert existing safety and quality gates into a release | Reliable ck: intended-use statement, scenario test matrix, incident metrics, release sign-off, and accessible privacy/data controls. | [UK product-safety standards][2] |
| Evidence for conversational AI wellbeing outcomes is heterogeneous, while privacy, bias, and safety risks remain material. User experience depends strongly on communication quality and user trust. | Measure helpfulness and calibrated trust separately from engagement; use source visibility and uncertainty language rather than fluent but unsupported reassurance. | [Systematic review][3] |

## Discovery constraints

The public product domain is `askmukthiguru.lovable.app`. SimilarWeb rank, visits, and traffic-source requests were attempted for May–July 2026 but could not run becThe public product domain is `askmukthiguru.lovable.app`. SimilarWeb rank, visits, and traffic-source requests were attempted for May–July 2026 but could not run becThe public product domain is `askmukthiguru.lovable.app`. SimilarWeb rank, visits, and traffic-source requests were attempted for May–July 2026 but could not run becThe public product domain is `askmukthiguru.lovable.app`. SimilarWeb rank, visits, and traffic-scenario matrix.** Make intended use, prohibited claims, crisis boundaries, retrieval-confidence behaviour, and release-test evidence auditable in one versioned place.
2. **Calibrated-trust UX.** Expand the existing provenance indicator into response-level source excerpts, “what this answer is based on,” and clear low-evidence fallback copy.
3. **Privacy and dependency guardrails.** Add plain-language data controls, session breaks for high-intensity use, and non-anthropomorphic reminder language; validate with user research before enforcing limits.
4. **Evaluation and observability adoption.** Assess mature open-source evaluation/trace tools against self-hosting, data-residency, and model-provider constraints before adoption; do not add a new telemetry dependency solely because it is popular.

## References

[1]: https://www.apa.org/topics/artificial-intelligence-machine-learning/health-advisory-chatbots-wellness-apps "American Psychological Association: Health advisory on generative AI chatbots and wellness apps"
[2]: https://www.gov.uk/government/publications/generative-ai-product-safety-standards/generative-ai-product-safety-standards "UK Government: Generative AI product safety standards"
[3]: https://www.nature.com/articles/s41746-023-00979-5 "Systematic review and meta-analysis of AI-based conversational agents for mental health and well-being"

## Open-source assessment

| Project | Maturity signal at review | Licence | Fit assessment | Decision |
|---|---:|---|---|---|
| [Ragas][4] | 15,281 GitHub stars; updated 2026-02-24 | Apache-2.0 | Focused RAG-quality evaluation candidate; can validate retrieval-context and answer-grounding changes in offline CI. | Evaluate in a sandbox spike; do not add to the production request path. |
| [DeepEval][5] | 17,537 GitHub stars; updated 2026-08-11 | Apache-2.0 | Broad LLM test framework suitable for deterministic regression scenarios and red-team fixtures. | Compare against the existing evaluation suite before adding a second framework. |
| [Arize Phoenix][6] | 10,999 GitHub stars; updated 2026-08-12 | Other | Observability/evaluation option; trace data may contain sensitive spiritual or distress disclosures. | Require self-hosting, data-flow review, and retention controls before any pilot. |
| [Langfuse][7] | 32,907 GitHub stars; updated 2026-08-11 | Other | Mature prompt, trace, dataset, and evaluation platform, but introduces data-governance and operational complexity. | Assess only after defining trace-redaction, consent, self-hosting, and retention requirements. |

> The repository discovery is a shortlisting exercise, not an endorsement or an integration. Adoption must pass licence, security, privacy, data-residency, operational-cost, and benchmark-value review.

[4]: https://github.com/vibrantlabsai/ragas "Ragas"
[5]: https://github.com/confident-ai/deepeval "DeepEval"
[6]: https://github.com/Arize-ai/phoenix "Arize Phoenix"
[7]: https://github.com/langfuse/langfuse "Langfuse"
