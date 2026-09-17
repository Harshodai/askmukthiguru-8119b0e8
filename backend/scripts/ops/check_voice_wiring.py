"""Regression checks for the failure class that made the voice work invisible.

Run:  .venv/bin/python -m scripts.ops.check_voice_wiring

This lives in scripts/ops/ rather than backend/tests/ because backend/tests/ is
owned by another workstream right now. It is a plain assert script with no test
framework — run it directly, or wire it into CI as one command.

THE FAILURE CLASS
-----------------
Three defects, all of which failed SILENTLY and all of which shipped:

1. A registered service that is always ``None`` in production.
   ``rag/nodes/_services.py:set_guru_brain()`` had zero callers, so
   ``get_guru_brain()`` always returned None and
   ``_fetch_guru_tone_style_block`` returned "" on every single request. The
   feature looked wired, was flag-enabled, and did nothing. Nothing failed.

2. A persona budget that truncates.
   ``GURU_SYSTEM_PROMPT`` is injected into a layer capped at
   ``generation_persona_token_budget`` (2048). When the persona grows past the
   cap, ``cap_to_token_budget`` silently cuts it mid-sentence and everything
   appended after it is discarded. No error, no log, just a prompt missing its
   tail. (I reintroduced this myself while editing the formatting rules on
   2026-09-15 and only caught it because of this check.)

3. A benchmark that scores its own reference.
   ``benchmarks/guru_voice_benchmark.py`` compared a hardcoded REFERENCE_VOICE
   against a rubric derived from that same string and reported 5.0/5.0. A
   metric that cannot fail is not a metric.
"""

from __future__ import annotations

import sys

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


def check_no_silently_dead_service() -> None:
    """A voice path must not depend on a setter nobody calls."""
    print("\n1. registered-but-never-set service")
    import inspect
    from pathlib import Path

    from rag.nodes import _services

    repo = Path(_services.__file__).resolve().parents[2]
    callers = [
        p
        for p in repo.rglob("*.py")
        if "set_guru_brain(" in p.read_text(encoding="utf-8", errors="ignore")
        and p.name != "_services.py"
    ]
    # This is still dead as of 2026-09-15 and is EXPECTED to be, because the
    # voice path no longer depends on it (see services/voice/register.py, which
    # needs no runtime registration). The check that matters is the second one:
    # nothing on the live voice path may depend on that setter.
    print(f"       set_guru_brain callers: {len(callers)} (0 is fine — path retired)")

    from services.voice import register as vr

    src = inspect.getsource(vr)
    check(
        "voice register does not depend on a runtime setter",
        "get_guru_brain" not in src and "set_" not in src,
        "services/voice/register.py must resolve profiles from disk, not registration",
    )
    # And it must actually produce a non-empty block, which is what the old
    # path failed to do.
    spec = vr.register_for("What is the Beautiful State?", docs=[{"teacher_id": "krishnaji"}])
    check("register produces a non-empty block", bool(spec.block.strip()))
    check(
        "register resolved a real profile", spec.certified, "run scripts.ops.build_voice_profiles"
    )


def check_persona_fits_budget() -> None:
    """The persona must survive its own token cap uncut."""
    print("\n2. persona token budget")
    from app.config import settings
    from rag.compressor import cap_to_token_budget
    from rag.prompts.system import GURU_SYSTEM_PROMPT

    budget = int(getattr(settings, "generation_persona_token_budget", 2048))
    capped = cap_to_token_budget(GURU_SYSTEM_PROMPT, budget)
    check(
        "GURU_SYSTEM_PROMPT is not truncated by its budget",
        len(capped) == len(GURU_SYSTEM_PROMPT),
        f"persona {len(GURU_SYSTEM_PROMPT)} chars exceeds budget {budget} tokens; "
        f"cap dropped {len(GURU_SYSTEM_PROMPT) - len(capped)} chars",
    )
    # The register rides OUTSIDE the persona layer precisely so it cannot be
    # eaten by this cap. Verify it is appended to a finished prompt, not nested.
    from services.voice.register import apply_register, register_for

    spec = register_for("What is the Beautiful State?", docs=[])
    combined = apply_register("BASE", spec)
    check("register is appended outside the persona layer", combined.startswith("BASE"))


def check_metric_cannot_self_score() -> None:
    """The voice metric must be falsifiable against a real negative control."""
    print("\n3. metric cannot score its own reference")
    from services.voice.style import load_profile, validate_profile

    machine = [
        "The transition from I-consciousness to One Consciousness reveals that true "
        "spiritual awakening extends far beyond personal liberation, ultimately creating "
        "a profound ripple effect. This transformative shift generally begins by healing "
        "the immediate family unit, which then uplifts the broader community and fosters "
        "a comprehensive sense of collective wellbeing among individuals.",
    ]
    human = [
        "You cannot hope that peace will happen to you on a perfect day sometime in the "
        "future while you allow your pain to linger in your heart every day for years. "
        "Peace has to become your reality now. The man who spoke to me had resigned "
        "himself. I helped him see that resignation is not peace. What is happening "
        "inside you as you read this?",
    ]
    for teacher in ("preethaji", "krishnaji", "preethaji_krishnaji", "ekam"):
        profile = load_profile(teacher)
        if profile is None:
            check(
                f"profile {teacher} exists", False, "run scripts.ops.build_voice_profiles --apply"
            )
            continue
        check(
            f"profile {teacher} was certified against a negative control",
            profile.is_certified,
            f"validation={profile.provenance.validation}",
        )
        report = validate_profile(profile, human, machine)
        check(
            f"profile {teacher} ranks human speech above machine prose",
            report.get("auc", 0.0) >= 0.75,
            f"auc={report.get('auc')}",
        )
        check(
            f"profile {teacher} was built from verbatim speech only",
            "raptor_level=0" in profile.provenance.verbatim_criteria
            or "verbatim" in profile.provenance.verbatim_criteria,
            profile.provenance.verbatim_criteria,
        )


def check_refusal_copy_is_seeker_facing() -> None:
    """No refusal surface may narrate internal machinery at a seeker."""
    print("\n4. refusal copy names no internal machinery")
    from rag.prompts.system import FALLBACK_RESPONSE
    from services.voice import register as vr

    banned = (
        "verification gate",
        "generated draft",
        "wisdom library",
        "retrieved excerpts",
        "pipeline",
        "evidence excerpt",
        "available passages",
    )
    surfaces = {
        "FALLBACK_RESPONSE": FALLBACK_RESPONSE,
        "PARTIAL_EVIDENCE_PREFACE": vr.PARTIAL_EVIDENCE_PREFACE,
        "NO_TEACHING_FOUND": vr.NO_TEACHING_FOUND,
        "CONFIDENCE_HEDGE": vr.CONFIDENCE_HEDGE,
        "REDACTION_NOTE_ONE": vr.REDACTION_NOTE_ONE,
    }
    for name, text in surfaces.items():
        hit = [b for b in banned if b in text.lower()]
        check(f"{name} is free of machinery talk", not hit, f"contains {hit}")

    # The abstention copy is matched by _EVIDENCE_REFUSAL_MARKERS to trigger the
    # one-shot evidence retry. If the copy changes and the marker does not, the
    # retry silently stops firing.
    from rag.nodes.generation import _EVIDENCE_REFUSAL_MARKERS

    check(
        "abstention copy is still matched by an evidence-refusal marker",
        any(m in vr.NO_TEACHING_FOUND.lower() for m in _EVIDENCE_REFUSAL_MARKERS),
        "NO_TEACHING_FOUND changed without updating _EVIDENCE_REFUSAL_MARKERS",
    )


def check_formatting_contract() -> None:
    """Prose by default; lists only where the seeker asked for steps."""
    print("\n5. formatting contract is conditional, not blanket")
    from rag.prompts.system import GURU_SYSTEM_PROMPT
    from services.voice.register import build_register, classify_shape

    check(
        "blanket bullet mandate is gone",
        "must be its own bullet" not in GURU_SYSTEM_PROMPT,
    )
    check(
        "decorative bullet markers are forbidden",
        "✦" in GURU_SYSTEM_PROMPT and "Never use" in GURU_SYSTEM_PROMPT,
        "the prompt should name ✦/▸ only to forbid them",
    )
    check(
        "duplicate word-count budget removed from persona",
        "100–200 words" not in GURU_SYSTEM_PROMPT and "150–250 words" not in GURU_SYSTEM_PROMPT,
        "length budgets must live only in response_length_instruction",
    )
    check(
        "doctrine question routes to prose",
        not build_register(
            "preethaji", classify_shape("What is the Beautiful State?")
        ).allows_lists,
    )
    check(
        "steps question routes to a list",
        build_register(
            "preethaji", classify_shape("What are the exact 6 steps of Soul Sync?")
        ).allows_lists,
    )
    check(
        "distress never routes to a list",
        not build_register("preethaji", classify_shape("x", intent="DISTRESS")).allows_lists,
    )


def check_cache_safety() -> None:
    """Voice selection must not vary per user, or the shared cache leaks."""
    print("\n6. voice selection is cache-safe")
    import ast
    import inspect
    import textwrap

    from services.voice import register as vr

    def code_only(fn) -> str:
        """Source with docstrings stripped — prose that NAMES a forbidden key
        (e.g. "takes no GraphState") must not read as a use of it."""
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                body = getattr(node, "body", [])
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    node.body = body[1:]
        return ast.unparse(tree)

    src = code_only(vr.register_for) + "\n" + code_only(vr.select_teacher)
    for forbidden in ("user_id", "memory_context", "tenant_id", "GraphState"):
        check(f"register_for/select_teacher do not read {forbidden}", forbidden not in src)
    docs = [{"teacher_id": "krishnaji"}]
    a = vr.register_for("What is the Beautiful State?", intent="FACTUAL", docs=docs)
    b = vr.register_for("What is the Beautiful State?", intent="FACTUAL", docs=docs)
    check("same question + same docs yields an identical register", a.block == b.block)


def main() -> int:
    print("voice wiring regression checks")
    check_no_silently_dead_service()
    check_persona_fits_budget()
    check_metric_cannot_self_score()
    check_refusal_copy_is_seeker_facing()
    check_formatting_contract()
    check_cache_safety()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {FAILURES}")
        return 1
    print("all voice wiring checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
