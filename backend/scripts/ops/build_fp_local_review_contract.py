#!/usr/bin/env python3
"""Write the owner-only local-review contract, pinning every artifact by sha256.

**Read-only** with respect to the corpus: it reads artifact files and writes
one small JSON contract. It never contacts Qdrant, never mutates an alias,
never touches Redis and never changes an environment variable.

The contract is what makes the local review mode fail closed: the service
refuses to start when a pinned artifact is missing, unreadable, or whose
sha256 no longer matches. Regenerating the contract after a deliberate corpus
change is an explicit, reviewable act — it is not something a stale manifest
can do by itself.

Usage
-----
    python -m scripts.ops.build_fp_local_review_contract \\
        --out backend/config/first_person_local_review.json \\
        --tiers-manifest audits/evidence/public_release_phase4_tiers_manifest_2026-10-22.json \\
        --verdicts audits/evidence/public_release_phase2_verdicts_2026-10-22.json \\
        --rights-manifest audits/evidence/public_release_phase4_rights_manifest_2026-10-22.json \\
        --rights-join audits/evidence/public_release_phase4_rights_join_2026-10-22.jsonl \\
        --speaker-conflicts audits/evidence/public_release_phase4_speaker_conflicts_2026-10-22.jsonl \\
        --serving-contract backend/config/first_person_serving_contract.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA = "fp-local-review-contract-v1"
TIER = "local_review_candidate"
EVIDENCE_POLICY = "automated_evidence_candidate"
# The canonical owner-only label. The service refuses to start when a
# contract pins a different one, so the label can never drift.
REVIEW_LABEL = "\n".join(
    (
        "REVIEW CANDIDATE — NOT PUBLIC RELEASE",
        "AUTOMATED EVIDENCE — NOT HUMAN-CERTIFIED ATTRIBUTION",
    )
)


class ContractBuildError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("--tiers-manifest", required=True)
    parser.add_argument("--verdicts", required=True)
    parser.add_argument("--rights-manifest", required=True)
    parser.add_argument("--rights-join", required=True)
    parser.add_argument("--speaker-conflicts", required=True)
    parser.add_argument(
        "--deterministic-id-collisions",
        default=None,
        help="collision artifact; the mode refuses to serve a span whose rebuilt id "
        "identifies more than one source span",
    )
    parser.add_argument("--serving-contract", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--max-clips", type=int, default=3)
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()

    def _pin(relative: str) -> dict[str, str]:
        path = Path(relative)
        if not path.is_absolute():
            path = root / path
        if not path.is_file():
            print(f"[fp-local-review-contract] missing artifact: {path}", file=sys.stderr)
            raise SystemExit(2)
        try:
            relative_to_root = str(path.resolve().relative_to(root))
        except ValueError:
            relative_to_root = str(path.resolve())
        return {"path": relative_to_root, "sha256": _sha256_file(path)}

    contract: dict[str, Any] = {
        "schema": SCHEMA,
        "enabled": False,
        "allow_in_production": False,
        "note": (
            "Owner-only, file-backed first-person review candidate preview. It never "
            "reads or writes Qdrant, never touches the 'first_person' alias, and "
            "never calls an LLM to write teaching text. 'enabled' is the explicit "
            "local-only flag: the route refuses to run unless the environment sets "
            "FIRST_PERSON_LOCAL_REVIEW_ENABLED=true AND IS_PRODUCTION is false."
        ),
        "tier": TIER,
        "tiers_manifest": _pin(args.tiers_manifest),
        "verdicts": _pin(args.verdicts),
        "rights_manifest": _pin(args.rights_manifest),
        "rights_join": _pin(args.rights_join),
        "speaker_conflicts": _pin(args.speaker_conflicts),
        "serving_contract": _pin(args.serving_contract),
        "corpus_version": "fp-context-transcript-v2",
        "evidence_policy": EVIDENCE_POLICY,
        "review_label": REVIEW_LABEL,
        "max_clips": args.max_clips,
    }
    if args.deterministic_id_collisions:
        contract["deterministic_id_collisions"] = _pin(args.deterministic_id_collisions)

    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[fp-local-review-contract] wrote {out}")
    for key in (
        "tiers_manifest",
        "verdicts",
        "rights_manifest",
        "rights_join",
        "speaker_conflicts",
        "serving_contract",
        "deterministic_id_collisions",
    ):
        if key not in contract:
            continue
        print(f"[fp-local-review-contract] {key}: {contract[key]['sha256'][:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
