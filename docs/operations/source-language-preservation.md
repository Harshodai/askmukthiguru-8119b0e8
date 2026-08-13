# Source-language preservation in translation

Answer translation may change explanatory prose for a chosen language, but it must not silently change the identity, ordering, or language of cited source material. Citation URLs and source records remain untouched in the response envelope; only textual `[N]` markers inside translated answer prose are protected here.

The routed translation provider now applies a provider-independent marker restoration step after Gemini, Sarvam, or Ollama returns translated text. If a provider omits a marker, the missing source marker is appended in source order. If it preserves a grouped marker such as `[2, 1]`, the safeguard recognises both numbers and does not duplicate them.

| Release check | Evidence |
|---|---|
| Marker survival | `backend/tests/test_translation_citation_markers.py` passes. |
| Provider routing | Gemini and routing-provider translation regressions pass. |
| Human language quality | The priority-language reviewer artifact approves fluency, culturally appropriate phrasing, and faithful source context. |
| Source fidelity | Citations remain source-language records; do not translate URLs, source identities, release versions, or quoted source excerpts without separately preserving the original. |

This safeguard does not claim that an automated marker check proves translation quality. Production promotion still requires reviewed priority-language results from the language evaluation gate.
