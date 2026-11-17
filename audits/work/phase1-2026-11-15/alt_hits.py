"""Read-only: per-alternative hit counts of the serving-gate regexes over stored clips.

Usage: backend/.venv/bin/python3 alt_hits.py <collection> [<collection> ...]
Run with cwd = backend/ so `services` imports resolve.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from collections import Counter

QDRANT = "http://localhost:6333"


def split_top_level(src: str) -> list[str]:
    """Split a regex source on '|' at paren depth 0, respecting escapes and classes."""
    parts, buf, depth, in_class, i = [], [], 0, False, 0
    while i < len(src):
        ch = src[i]
        if ch == "\\":
            buf.append(src[i : i + 2])
            i += 2
            continue
        if in_class:
            in_class = ch != "]"
        elif ch == "[":
            in_class = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "|" and depth == 0:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return [p for p in parts if p]


def unwrap(src: str) -> str:
    """Strip one enclosing \\b(?: ... )\\b wrapper so inner alternatives are visible."""
    m = re.fullmatch(r"\\b\(\?:(.*)\)\\b", src, re.S)
    return m.group(1) if m and len(split_top_level(src)) == 1 else src


def scroll(collection: str):
    offset = None
    while True:
        body = {"limit": 512, "with_payload": ["verbatim_text"], "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        req = urllib.request.Request(
            f"{QDRANT}/collections/{collection}/points/scroll",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.load(resp)["result"]
        for point in result["points"]:
            yield str(point["id"]), str((point.get("payload") or {}).get("verbatim_text") or "")
        offset = result.get("next_page_offset")
        if offset is None:
            return


def main() -> None:
    import services.first_person_content_assessment as ca

    families = {
        "CLINICAL": ca._CLINICAL_SRC,
        "CAUSAL_ETIOLOGY": ca._CAUSAL_ETIOLOGY_SRC,
        "OUTCOME_PROMISE": ca.OUTCOME_PROMISE_RE.pattern,
        "EVENT_MARKER": ca.EVENT_MARKER_RE.pattern,
        "WELLBEING_FRAMING": ca.WELLBEING_FRAMING_RE.pattern,
        "GRAPHIC_VIOLENCE": ca.GRAPHIC_VIOLENCE_RE.pattern,
        "PRACTICE_INVITATION": ca.PRACTICE_INVITATION_RE.pattern,
    }
    for collection in sys.argv[1:]:
        clips = list(scroll(collection))
        print(f"\n===== {collection}: {len(clips)} points, {sum(1 for _, t in clips if t)} with verbatim_text")
        for name, src in families.items():
            alts = split_top_level(unwrap(src))
            wrapped = unwrap(src) != src
            compiled = []
            for alt in alts:
                pattern = rf"\b(?:{alt})\b" if wrapped else alt
                compiled.append((alt, re.compile(pattern, re.IGNORECASE)))
            whole = re.compile(src, re.IGNORECASE)
            family_hits = sum(1 for _, t in clips if whole.search(t))
            per_alt = Counter()
            sole = Counter()  # clips blocked by exactly one alternative
            for _, text in clips:
                matched = [alt for alt, rx in compiled if rx.search(text)]
                for alt in matched:
                    per_alt[alt] += 1
                if len(matched) == 1:
                    sole[matched[0]] += 1
            zero = [a for a, _ in compiled if per_alt[a] == 0]
            one = [a for a, _ in compiled if per_alt[a] == 1]
            few = [a for a, _ in compiled if 2 <= per_alt[a] <= 5]
            print(
                f"\n[{name}] alternatives={len(compiled)} clips_hit={family_hits} "
                f"| alts hitting 0 clips={len(zero)}, exactly 1={len(one)}, 2-5={len(few)}, "
                f">5={len(compiled) - len(zero) - len(one) - len(few)}"
            )
            top = per_alt.most_common(6)
            print("  top:", "; ".join(f"{a[:38]!r}={n} (sole {sole[a]})" for a, n in top))
            if zero:
                print("  zero-hit sample:", "; ".join(repr(a[:40]) for a in zero[:6]))


if __name__ == "__main__":
    main()
