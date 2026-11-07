"""Unit tests for T7-05: Exception ratchet (CQ-006) and Import layer architecture guard (CQ-007)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.guards.exception_ratchet import parse_baseline, scan_exceptions
from scripts.guards.import_layer_lint import load_allowlist, scan_layer_violations


def test_exception_ratchet_baseline_respected():
    baseline_path = REPO_ROOT / "scripts" / "guards" / "exception_baseline.txt"
    max_broad, max_swallows, max_swallows_fp = parse_baseline(baseline_path)

    broad_count, all_swallows, silent_swallows_fp = scan_exceptions(REPO_ROOT)

    assert broad_count <= max_broad, (
        f"Broad exception count {broad_count} exceeded baseline ceiling {max_broad}"
    )
    assert len(all_swallows) <= max_swallows, (
        f"Silent swallows count {len(all_swallows)} exceeded baseline ceiling {max_swallows}"
    )
    assert len(silent_swallows_fp) <= max_swallows_fp, (
        f"Silent swallows in first-person services {len(silent_swallows_fp)} exceeded ceiling {max_swallows_fp}"
    )


def test_import_layer_lint_clean():
    allowlist_path = REPO_ROOT / "scripts" / "guards" / "import_layer_allowlist.txt"
    allowlist = load_allowlist(allowlist_path)

    # Acceptance criteria: <= 25 justified lazy imports
    assert len(allowlist) <= 25, (
        f"Grandfathered cross-layer imports {len(allowlist)} exceeded ceiling 25"
    )

    violations = scan_layer_violations(REPO_ROOT)
    assert violations == [], f"Found illegal upward architecture layer imports: {violations}"
