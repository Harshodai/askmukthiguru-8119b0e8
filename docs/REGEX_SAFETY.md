# Regex Safety and Performance Policy

AskMukthiGuru uses regular expressions in validation, URL classification, multilingual text handling, PII scanning, Markdown extraction, and response cleanup. Regex is appropriate when the language is regular and the pattern is short, static, and bounded. It is not a universal replacement for a parser, URL library, JSON decoder, or ordinary string operations.

## Audit result

The August 2026 inventory found **641 regex call sites across 181 source files** in backend, frontend, scripts, and Supabase-related code, excluding the immutable transcript corpus, generated assets, and dependencies. The dominant operations were `re.sub` (189), `re.compile` (177), `re.search` (129), and `re.findall` (82). The scan found no canonical unbounded nested-quantifier literals in runtime Python code after excluding tests and bounded parsing patterns.

The new `scripts/security/check_regex_safety.py` scanner is deliberately narrow. It rejects the canonical unbounded nested-repetition class such as `^(a+)+$`, which OWASP identifies as a ReDoS risk [1]. It does not claim that every regex is automatically linear-time; review remains required for dynamic patterns, unbounded input, backtracking-heavy lookarounds, and regexes used in hot loops.

## Engineering rules

| Situation | Preferred approach |
| --- | --- |
| Fixed vocabulary or a small set of intent markers | Precompiled static regex or normalized string membership |
| User-controlled literal inserted into a pattern | Escape with `re.escape`; never treat it as regex syntax |
| JSON, HTML, URLs, or structured documents | Use the relevant parser or URL library first; use regex only for a narrow residual check |
| Large or attacker-controlled text | Enforce an input-size limit before matching and avoid ambiguous nested repetition |
| Repeated matching in a loop | Precompile the static pattern; use `finditer` rather than materializing large `findall` lists when appropriate |
| Need for arbitrary user-supplied patterns | Do not expose Python/JavaScript backtracking engines directly; use a linear-time engine such as RE2 or reject unsupported syntax [3] |
| Logic that is clearer with ordinary Python | Prefer `str.startswith`, `str.endswith`, `str.partition`, `str.split`, or a small parser; Python’s own HOWTO notes that complicated regexes may be less understandable than direct code [2] |

## Review checklist

Every new runtime regex should document its input source, maximum input size, expected operation, and why a parser or string operation is insufficient. Reviewers should look for nested unbounded quantifiers, overlapping alternation under repetition, backreferences, lookarounds over unbounded text, dynamic pattern construction, and whole-document `DOTALL` extraction. A match timeout or process boundary is still required when an untrusted pattern cannot be avoided.

The scanner runs in the backend CI workflow and is fail-closed. The associated regression test proves that the scanner rejects the canonical ReDoS shape and accepts a bounded title-name pattern. It intentionally does not scan tests, the immutable corpus, or generated dependencies.

## References

[1]: https://owasp.org/www-community/attacks/Regular_expression_Denial_of_Service_-_ReDoS "OWASP: Regular expression Denial of Service - ReDoS"

[2]: https://docs.python.org/3/howto/regex.html "Python Regular Expression HOWTO"

[3]: https://github.com/google/re2 "Google RE2: safe linear-time regular-expression engine"
