#!/usr/bin/env python3
"""Word-timed resegmentation v2 of ``first_person_v10`` (dry run by default).

Re-cuts clips from full word-timed transcripts (``transcripts_B/*.json``) so length and
completeness targets can be met, which merge-only v1 (``resegment_v10.py``) cannot do.

Rules (all measured/decided 2026-11-16, see the constants):
* Teacher speech only. Speaker = the transcript's per-word label (K/P) mapped to the
  video's v10 ``guru_id`` set. Never inferred from text. A short O/? run flanked by the
  same teacher label is absorbed (diarisation noise); anything else breaks the parent.
* Segment at sentence ends, DP over each contiguous teacher run: grow to a complete thought,
  never end on a conjunction / promissory setup, never start on an orphan opener
  (v1's gate imports), cut at a sentence end before the cap. Clips never overlap.
* Text = exact transcript words of the window -> ``asr_cleaner``; both hashes = sha256(text).
* Voice verification is NOT carried over: a re-cut span has no per-span ECAPA verdict, so it is
  written ``speaker_verified=False`` / ``pending_voice_check`` (invariant 23; the store only
  serves ``speaker_verified=True``). Run the span-slice regenerator on the output to promote.
* ``source_span_id`` is the deterministic ``make_source_span_id`` id so ``SourceSpan`` validates.
  ``SourceSpan`` is ``extra="forbid"``, so the invariant-4 id is NOT stored in the payload (it would
  make every child unreadable); it is written to ``proposed_clips.jsonl`` (``inv4_point_id``).
* Videos whose word timing is not trustworthy keep their v10 clips unchanged and are flagged.

Usage (host python, cwd backend/):
    .venv/bin/python3 scripts/ops/resegment_v2.py --dry-run
    .venv/bin/python3 scripts/ops/resegment_v2.py --apply --snapshot-confirmed --approved-by NAME
"""

from __future__ import annotations

import argparse
import collections
import difflib
import functools
import glob
import json
import math
import os
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Optional

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import resegment_v10 as v1  # noqa: E402  (gates, hashing, apply guards, shadow-collection code)

CHUNKER_VERSION = "resegment_v2:words_v1"
CORPUS_VERSION = "fp-context-resegment-v2"
DEFAULT_OUT = v1._REPO / "audits" / "work" / "resegmentation-v2-2026-11-16"
DATA = Path.home() / "mukthiguru_attribution_data"
V1_DIR = v1._REPO / "audits" / "work" / "resegmentation-2026-11-16"

# Usable-video rule, written before the count was looked at (2026-11-16).
USABLE_MIN_SIM = 0.80  # median per-clip word similarity: v10 text vs transcript words in its own +-300 ms window
USABLE_MIN_ALIGNED = 0.90  # fraction of words with aligned=True
# Speaker smoothing / run rules.
ABSORB_MAX_S, ABSORB_MAX_WORDS = 2.5, 10  # O/? run flanked by the same teacher on both sides
MAX_INTRA_GAP_MS = 2500  # larger silence ends the sentence and the parent (v1 used 1500 between spans)
# Segmentation cost (lower is better); ideal 18-25 s per invariant 11.
IDEAL_S, SOFT_CAP_S, WINDOW_S = 22.0, 60.0, 100.0
SOFT_PIECE_S, SOFT_PIECE_GAP_MS = 15.0, 300  # unpunctuated speech: cut a >15 s sentence at a pause
MIN_S = 8.0
DEFECT_COST, CONTENT_COST, SHORT_WORDS_COST, CLIP_COST = 6.0, 4.0, 20.0, 1.0
_ABBREV = {"mr.", "mrs.", "ms.", "dr.", "st.", "vs.", "no.", "sri.", "etc."}
_TERMINAL = re.compile(r"[.!?][\"'”’)\]]*$")
CODE_OF = {"krishnaji": "K", "preethaji": "P"}
SPEAKER_NAME = {"krishnaji": "Sri Krishnaji", "preethaji": "Sri Preethaji"}

v1.standalone_problem = functools.lru_cache(maxsize=1_000_000)(v1.standalone_problem)  # pure; DP re-asks the same text


# ---------------------------------------------------------------- transcripts
def _word_sim(a: str, b: str) -> float:
    norm = lambda t: re.sub(r"[^a-z0-9 ]", "", t.lower()).split()  # noqa: E731
    na, nb = norm(a), norm(b)
    return difflib.SequenceMatcher(None, na, nb, autojunk=False).ratio() if na and nb else 0.0


def load_words(path: str) -> list[dict[str, Any]]:
    return [{"i": i, "w": str(x["w"]), "s": int(round(x["start"] * 1000)), "e": int(round(x["end"] * 1000)),
             "spk": x.get("spk") or "?", "al": x.get("aligned") is True} for i, x in enumerate(json.load(open(path)))]


def score_transcript(words: list[dict[str, Any]], v10: list[dict[str, Any]]) -> tuple[float, float]:
    sims = []
    for c in v10[:20]:
        win = " ".join(x["w"] for x in words if x["s"] >= c["start_ms"] - 300 and x["e"] <= c["end_ms"] + 300)
        sims.append(_word_sim(c["verbatim_text"], win))
    aligned = sum(x["al"] for x in words) / max(1, len(words))
    return (statistics.median(sims) if sims else 0.0), aligned


def pick_transcripts(v10_by_video: dict[str, list[dict[str, Any]]], data: Path = DATA) -> dict[str, dict[str, Any]]:
    """Per v10 video: the transcripts_B file with the best v10 similarity (ties: more aligned words)."""
    files: dict[str, list[str]] = collections.defaultdict(list)
    for pat in ("*/transcripts_B/*.json", "*/*/transcripts_B/*.json"):
        for f in sorted(glob.glob(str(data / pat))):
            files[os.path.basename(f)[:-5]].append(f)
    out: dict[str, dict[str, Any]] = {}
    for vid, clips in v10_by_video.items():
        best: Optional[dict[str, Any]] = None
        for f in files.get(vid, []):
            words = load_words(f)
            sim, aligned = score_transcript(words, clips)
            cand = {"path": f, "words": words, "sim": sim, "aligned": aligned, "candidates": len(files[vid])}
            if best is None or (sim, aligned) > (best["sim"], best["aligned"]):
                best = cand
        if best is not None:
            best["usable"] = best["sim"] >= USABLE_MIN_SIM and best["aligned"] >= USABLE_MIN_ALIGNED
            out[vid] = best
    return out


# ---------------------------------------------------------------- speaker / sentences
def apply_v10_voice(words: list[dict[str, Any]], v10: list[dict[str, Any]],
                    code_guru: dict[str, str]) -> tuple[list[str], int]:
    """Word labels where an O/? word that lies inside a speaker-verified v10 span of this video takes that
    span's teacher label: v10's ECAPA voice verdict is evidence about the audio, not about the text."""
    guru_code = {g: c for c, g in code_guru.items()}
    spans = [(c["start_ms"], c["end_ms"], guru_code[c["guru_id"]]) for c in v10
             if c.get("speaker_verified") is True and c["guru_id"] in guru_code]
    lab = [w["spk"] for w in words]
    n = 0
    for k, w in enumerate(words):
        if lab[k] in ("O", "?"):
            mid = (w["s"] + w["e"]) // 2
            for s0, e0, code in spans:
                if s0 <= mid <= e0:
                    lab[k] = code
                    n += 1
                    break
    return lab, n


def smooth_labels(words: list[dict[str, Any]], codes: set[str],
                  lab: Optional[list[str]] = None) -> tuple[list[str], int]:
    """Word labels with short O/? runs between two words of the same teacher relabelled. Returns (labels, absorbed)."""
    lab = list(lab) if lab is not None else [w["spk"] for w in words]
    absorbed = 0
    for code in codes:
        i = 0
        while i < len(lab):
            if lab[i] in ("O", "?") and i > 0 and lab[i - 1] == code:
                j = i
                while j < len(lab) and lab[j] in ("O", "?"):
                    j += 1
                if (j < len(lab) and lab[j] == code and j - i <= ABSORB_MAX_WORDS
                        and (words[j - 1]["e"] - words[i]["s"]) / 1000.0 <= ABSORB_MAX_S):
                    for k in range(i, j):
                        lab[k] = code
                    absorbed += j - i
                i = j
            else:
                i += 1
    return lab, absorbed


def split_sentences(words: list[dict[str, Any]], lab: list[str]) -> list[dict[str, Any]]:
    """Sentences end at terminal punctuation, a label change or a long silence (hard break), or at a
    pause once an unpunctuated stretch passes SOFT_PIECE_S. ``open_start``/``open_end`` mark a sentence
    cut by a hard break rather than by its own punctuation: it is a fragment of a sentence the teacher
    run does not contain."""
    sents: list[dict[str, Any]] = []
    cur: list[int] = []
    prev_hard_open = False
    for k, w in enumerate(words):
        cur.append(k)
        last = k + 1 == len(words)
        term = bool(_TERMINAL.search(w["w"])) and w["w"].lower() not in _ABBREV
        hard = last or lab[k + 1] != lab[k] or words[k + 1]["s"] - w["e"] > MAX_INTRA_GAP_MS
        soft = (not last and not hard and w["e"] - words[cur[0]]["s"] > SOFT_PIECE_S * 1000
                and words[k + 1]["s"] - w["e"] >= SOFT_PIECE_GAP_MS)
        if term or hard or soft:
            aligned = [words[x] for x in cur if words[x]["al"]]
            sents.append({"a": cur[0], "b": cur[-1], "labels": {lab[x] for x in cur},
                          "s": min(x["s"] for x in aligned) if aligned else None,
                          "e": max(x["e"] for x in aligned) if aligned else None,
                          "wc": len(cur), "text": " ".join(words[x]["w"] for x in cur),
                          "open_start": prev_hard_open, "open_end": hard and not term and not last})
            prev_hard_open = hard and not term
            cur = []
    return sents


def teacher_runs(sents: list[dict[str, Any]], codes: set[str]) -> tuple[list[dict[str, Any]], collections.Counter]:
    """Contiguous same-teacher sentence runs; returns (runs, reasons excluded sentences were dropped)."""
    runs: list[dict[str, Any]] = []
    excl: collections.Counter = collections.Counter()
    cur: Optional[dict[str, Any]] = None
    for s in sents:
        code = next(iter(s["labels"])) if len(s["labels"]) == 1 else None
        if s["s"] is None:
            reason = "unaligned"
        elif code in codes:
            reason = None
        elif code in ("O", "?"):
            reason = "host_or_unknown_speaker"
        elif code is None:
            reason = "mixed_labels"
        else:
            reason = "other_teacher_label"
        if reason:
            excl["sentences_" + reason] += 1
            excl["words_" + reason] += s["wc"]
            s["excluded"] = reason
            if cur is not None:
                _trim_edges(cur, excl)
            cur = None
            continue
        if cur is None or cur["code"] != code or s["s"] - cur["sents"][-1]["e"] > MAX_INTRA_GAP_MS:
            if cur is not None:
                _trim_edges(cur, excl)
            cur = {"code": code, "sents": []}
            runs.append(cur)
        cur["sents"].append(s)
    if cur is not None:
        _trim_edges(cur, excl)
    runs = [r for r in runs if r["sents"]]
    return runs, excl


def _trim_edges(run: dict[str, Any], excl: collections.Counter) -> None:
    """Drop a leading/trailing sentence that is only a fragment of a sentence cut by a hard break."""
    while run["sents"] and run["sents"][0]["open_start"]:
        s = run["sents"].pop(0)
        excl["sentences_partial_at_run_edge"] += 1
        excl["words_partial_at_run_edge"] += s["wc"]
        s["excluded"] = "partial_at_run_edge"
    while run["sents"] and run["sents"][-1]["open_end"]:
        s = run["sents"].pop()
        excl["sentences_partial_at_run_edge"] += 1
        excl["words_partial_at_run_edge"] += s["wc"]
        s["excluded"] = "partial_at_run_edge"


# ---------------------------------------------------------------- segmentation
MAX_EDGE_TRIM = 3


def trim_run_defects(sents: list[dict[str, Any]], excl: collections.Counter) -> None:
    """A run has no neighbour to repair its first/last sentence: drop a leading sentence that is an orphan
    opener and a trailing one that is a dangling/promissory setup (never start on an orphan, never end on a
    setup). Dropped words are counted, never hidden."""
    for _ in range(MAX_EDGE_TRIM):
        if len(sents) > 1 and "bwd" in v1.boundary_kinds(sents[0]["text"]):
            s = sents.pop(0)
            excl["words_trimmed_run_head_defect"] += s["wc"]
            s["excluded"] = "trimmed_run_head_defect"
        else:
            break
    for _ in range(MAX_EDGE_TRIM):
        if len(sents) > 1 and "fwd" in v1.boundary_kinds(sents[-1]["text"]):
            s = sents.pop()
            excl["words_trimmed_run_tail_defect"] += s["wc"]
            s["excluded"] = "trimmed_run_tail_defect"
        else:
            break


def _clip_cost(text: str, dur: float, words: int) -> float:
    cost = CLIP_COST
    if dur < MIN_S:
        cost += 6 + (MIN_S - dur)
    elif dur > SOFT_CAP_S:
        cost += 4 + (dur - SOFT_CAP_S) / 4
    cost += 2 * abs(math.log(max(dur, 0.5) / IDEAL_S))
    if words < v1.MIN_WORDS:
        cost += SHORT_WORDS_COST
    kinds = v1.boundary_kinds(text)
    cost += DEFECT_COST * len(kinds)
    cp = v1.content_problem(text)
    if cp:
        cost += CONTENT_COST
    return cost


def cut_run(sents: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """Min-cost partition of a run into consecutive sentence groups (i, j inclusive). Covers every sentence."""
    n = len(sents)
    best = [math.inf] * (n + 1)
    prev = [0] * (n + 1)
    best[0] = 0.0
    for i in range(n):
        text, words = "", 0
        for j in range(i, n):
            dur = (sents[j]["e"] - sents[i]["s"]) / 1000.0
            if j > i and dur > WINDOW_S:
                break
            text = f"{text} {sents[j]['text']}".strip()
            words += sents[j]["wc"]
            c = best[i] + _clip_cost(text, dur, words)
            if c < best[j + 1]:
                best[j + 1], prev[j + 1] = c, i
    cuts, j = [], n
    while j > 0:
        cuts.append((prev[j], j - 1))
        j = prev[j]
    return cuts[::-1]


# ---------------------------------------------------------------- payloads
def _clip_payload(video: str, guru: str, words: list[dict[str, Any]], grp: list[dict[str, Any]],
                  base: dict[str, Any], art_sha: str) -> Optional[dict[str, Any]]:
    from domain.first_person_context import make_source_span_id
    from domain.speaker_provenance import pending_voice_fields
    from ingest.verbatim.asr_cleaner import clean_verbatim_text

    a, b = grp[0]["a"], grp[-1]["b"]
    raw = " ".join(words[k]["w"] for k in range(a, b + 1))
    text = clean_verbatim_text(raw)
    if not text.strip():
        return None
    h = v1._sha(text)
    al = [words[k] for k in range(a, b + 1) if words[k]["al"]]
    p = {k: base[k] for k in ("rights_cleared", "domain_rights_status", "caption_status", "source_url",
                              "asr_engine", "asr_model_version") if k in base}
    p.update(
        schema_version="fp-context-v1", corpus_version=CORPUS_VERSION, guru_id=guru, video_id=video,
        source_asset_id=video, speaker_id=guru, speaker_role="guru", start_ms=min(x["s"] for x in al),
        end_ms=max(x["e"] for x in al), word_start=a, word_end=b + 1, source_transcript_text=raw,
        verbatim_text=text, transcript_hash=h, source_text_hash=h, is_verbatim=True,
        provenance_kind="speech_turn_span", answer_role="direct", retrieval_text_version="fp-retrieval-v1",
        quality_status="verified_verbatim", source_artifact_sha256=art_sha, **pending_voice_fields(),
    )
    p["source_span_id"] = make_source_span_id(guru_id=guru, video_id=video, corpus_version=CORPUS_VERSION,
                                              word_start=a, word_end=b + 1, transcript_hash=h)
    clean_issue = v1.standalone_problem(text) or v1.boundary_kinds(text)
    p["boundary_status"] = "uncertain" if clean_issue else "verified"
    p["completeness_status"] = "uncertain" if clean_issue else "complete"
    return p


def build_video(video: str, tr: dict[str, Any], v10: list[dict[str, Any]], v10_parents: list[dict[str, Any]],
                *, art_sha: str) -> dict[str, Any]:
    """Pure function of (words, v10 metadata). Returns clips (payloads), parents, drops and counters."""
    words = tr["words"]
    gurus = sorted({c["guru_id"] for c in v10})
    codes = {CODE_OF[g] for g in gurus if g in CODE_OF}
    code_guru = {CODE_OF[g]: g for g in gurus if g in CODE_OF}
    base = v10[0]
    for f in ("rights_cleared", "domain_rights_status", "caption_status", "source_url", "asr_engine",
              "asr_model_version"):
        assert len({str(c.get(f)) for c in v10}) == 1, f"{video}: {f} is not single-valued in v10"
    lab, voiced = apply_v10_voice(words, v10, code_guru)
    lab, absorbed = smooth_labels(words, codes, lab)
    other_teacher = sum(1 for w, lb in zip(words, lab) if lb in ("K", "P") and lb not in codes)
    sents = split_sentences(words, lab)
    runs, excl = teacher_runs(sents, codes)
    excl["words_absorbed_into_teacher_runs"] = absorbed
    excl["words_relabelled_by_v10_verified_voice_span"] = voiced
    excl["words_other_teacher_label"] = other_teacher
    clips: list[dict[str, Any]] = []
    runs_out: list[list[dict[str, Any]]] = []
    short: list[dict[str, Any]] = []
    for run in runs:
        guru = code_guru[run["code"]]
        group: list[dict[str, Any]] = []
        trim_run_defects(run["sents"], excl)
        if not run["sents"]:
            continue
        for i, j in cut_run(run["sents"]):
            grp = run["sents"][i:j + 1]
            p = _clip_payload(video, guru, words, grp, base, art_sha)
            if p is None or v1._words(p["verbatim_text"]) < v1.MIN_WORDS or (grp[-1]["e"] - grp[0]["s"]) < MIN_S * 1000:
                short.append({"video_id": video, "start_ms": grp[0]["s"], "end_ms": grp[-1]["e"],
                              "words": sum(s["wc"] for s in grp), "reason": "under_min_words_or_8s"})
                for s_ in grp:
                    s_["excluded"] = "short_run_dropped"
                continue
            if group and p["start_ms"] < group[-1]["end_ms"]:
                p["start_ms"] = group[-1]["end_ms"]  # transcript times can overlap by a few ms; never overlap clips
            if p["end_ms"] <= p["start_ms"]:
                continue
            group.append(p)
        if group:
            runs_out.append(group)
            clips += group
    return {"clips": clips, "runs": runs_out, "short": short, "excluded": dict(excl),
            "sentences": sents, "gurus": gurus, "parents_v10": v10_parents}


def assemble(runs_out: list[list[dict[str, Any]]], speaker_ids: dict[tuple[str, str], list[str]]) -> list[dict[str, Any]]:
    """Parent units (one per contiguous teacher run) + prev/next chains + turn ids. Mutates clip payloads."""
    parents = []
    for group in runs_out:
        first, last = group[0], group[-1]
        pid = v1._sha(f"{CORPUS_VERSION}|parent|{first['video_id']}|{first['guru_id']}|{first['word_start']}")
        for k, c in enumerate(group):
            c.update(parent_unit_id=pid, turn_id=f"{pid[:12]}:t{k}", turn_index=k, source_span_index=k,
                     previous_span_id=group[k - 1]["source_span_id"] if k else None,
                     next_span_id=group[k + 1]["source_span_id"] if k + 1 < len(group) else None)
        ok = all(c["boundary_status"] == "verified" and c["completeness_status"] == "complete" for c in group)
        parents.append({
            "schema_version": "fp-context-v1", "corpus_version": CORPUS_VERSION, "guru_id": first["guru_id"],
            "video_id": first["video_id"], "parent_unit_id": pid,
            "ordered_source_span_ids": [c["source_span_id"] for c in group],
            "start_ms": first["start_ms"], "end_ms": last["end_ms"],
            "parent_text_hash": v1._sha(" ".join(c["verbatim_text"] for c in group)),
            "speaker_ids": speaker_ids.get((first["video_id"], first["guru_id"])) or [SPEAKER_NAME.get(first["guru_id"], first["guru_id"])],
            "speaker_continuity": True, "boundary_status": "verified" if ok else "uncertain",
            "completeness_status": "complete" if ok else "uncertain", "host_question_span_id": None,
            "parent_version": "parent-v1", "record_type": "parent_unit"})
    return parents


def drop_duplicate_texts(clips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove later copies of identical text (any video/guru pair handled like v1: same guru only)."""
    seen: dict[tuple[str, str], str] = {}
    dropped = []
    for c in sorted(clips, key=lambda c: (c["video_id"], c["start_ms"])):
        key = (v1._sha(c["verbatim_text"]), c["guru_id"])
        if key in seen:
            dropped.append(c["source_span_id"])
        else:
            seen[key] = c["source_span_id"]
    return dropped


# ---------------------------------------------------------------- orchestration
def point_id_pair(p: dict[str, Any]) -> tuple[str, str]:
    return v1.point_ids(p)


def validate_models(clips: list[dict[str, Any]], parents: list[dict[str, Any]]) -> dict[str, int]:
    from domain.first_person_context import ParentUnit, SourceSpan
    from domain.speaker_provenance import speaker_write_violations

    bad_child = bad_parent = bad_speaker = 0
    for c in clips:
        try:
            SourceSpan.model_validate({k: v for k, v in c.items() if k != "record_type"})
        except Exception:  # noqa: BLE001 - counted and reported, not swallowed
            bad_child += 1
        bad_speaker += bool(speaker_write_violations(c))
    for p in parents:
        try:
            ParentUnit.model_validate({k: v for k, v in p.items() if k != "record_type"})
        except Exception:  # noqa: BLE001
            bad_parent += 1
    return {"children_validated": len(clips), "children_invalid": bad_child, "parents_validated": len(parents),
            "parents_invalid": bad_parent, "speaker_write_violations": bad_speaker}


def run(points: list[dict[str, Any]], data: Path = DATA, only: Optional[set[str]] = None) -> dict[str, Any]:
    children = [{**p["payload"], "_id": p["id"]} for p in points if p["payload"].get("record_type") == "retrieval_child"]
    parents10 = [p["payload"] for p in points if p["payload"].get("record_type") == "parent_unit"]
    by_video: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for c in children:
        by_video[c["video_id"]].append(c)
    if only:
        by_video = {k: v for k, v in by_video.items() if k in only}
    trs = pick_transcripts(by_video, data)
    spk_ids: dict[tuple[str, str], list[str]] = {}
    for p in parents10:
        spk_ids.setdefault((p["video_id"], p["guru_id"]), list(p["speaker_ids"]))
    new_clips: list[dict[str, Any]] = []
    new_parents: list[dict[str, Any]] = []
    carried: list[dict[str, Any]] = []
    per_video: dict[str, Any] = {}
    shorts: list[dict[str, Any]] = []
    for vid in sorted(by_video):
        v10 = sorted(by_video[vid], key=lambda c: c["start_ms"])
        tr = trs.get(vid)
        if tr is None or not tr["usable"]:
            carried += v10
            per_video[vid] = {"status": "carried_v10_unchanged", "v10_clips": len(v10),
                              "sim": None if tr is None else round(tr["sim"], 3),
                              "aligned": None if tr is None else round(tr["aligned"], 3)}
            continue
        art = v1._sha(Path(tr["path"]).read_text())
        res = build_video(vid, tr, v10, [], art_sha=art)
        parents = assemble(res["runs"], spk_ids)
        new_clips += res["clips"]
        new_parents += parents
        shorts += res["short"]
        words = tr["words"]
        tsec = sum(w["e"] - w["s"] for w in words) / 1000.0
        csec = sum(c["end_ms"] - c["start_ms"] for c in res["clips"]) / 1000.0
        v10sec = sum(c["end_ms"] - c["start_ms"] for c in v10) / 1000.0
        per_video[vid] = {"status": "recut", "transcript_file": tr["path"].replace(str(Path.home()), "~"),
                          "transcript_candidates": tr["candidates"], "sim": round(tr["sim"], 3),
                          "aligned": round(tr["aligned"], 3), "v10_clips": len(v10), "v2_clips": len(res["clips"]),
                          "v10_seconds": round(v10sec, 1), "v2_seconds": round(csec, 1),
                          "transcript_word_seconds": round(tsec, 1), "excluded": res["excluded"],
                          "short_runs_dropped": len(res["short"])}
        per_video[vid]["_sentences"] = [(s["s"], s["e"], s.get("excluded")) for s in res["sentences"]]
    dup_ids = set(drop_duplicate_texts(new_clips))
    if dup_ids:
        new_clips = [c for c in new_clips if c["source_span_id"] not in dup_ids]
        runs = collections.defaultdict(list)
        for c in new_clips:
            runs[c["parent_unit_id"]].append(c)
        new_parents = assemble([sorted(g, key=lambda c: c["start_ms"]) for g in runs.values()], spk_ids)
    return {"clips": new_clips, "parents": new_parents, "carried": carried, "per_video": per_video,
            "short": shorts, "dup_dropped": len(dup_ids), "v10_children": children, "v10_parents": parents10}


# ---------------------------------------------------------------- scorecard
def gate_strict(text: str) -> bool:
    return (v1.standalone_problem(text) is None and not v1.boundary_kinds(text)
            and v1.MIN_WORDS <= v1._words(text) <= v1.MAX_WORDS)


def fidelity(v10: list[dict[str, Any]], v2: list[dict[str, Any]], per_video: dict[str, Any]) -> dict[str, Any]:
    """How much v10 text is recoverable from v2 clips of the same video, and why the rest is not."""
    norm = lambda t: re.sub(r"[^a-z0-9 ]", "", t.lower()).split()  # noqa: E731
    by: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for c in v2:
        by[c["video_id"]].append(c)
    rec, single, lost = [], 0, collections.Counter()
    got_words = all_words = 0
    for c in v10:
        pv = per_video.get(c["video_id"], {})
        if pv.get("status") != "recut":
            continue
        a = norm(c["verbatim_text"])
        near = [x for x in by[c["video_id"]] if x["end_ms"] > c["start_ms"] and x["start_ms"] < c["end_ms"]]
        near.sort(key=lambda x: x["start_ms"])

        def matched(b: list[str]) -> float:
            sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
            return sum(m.size for m in sm.get_matching_blocks() if m.size >= 3) / max(1, len(a))

        union = matched(norm(" ".join(x["verbatim_text"] for x in near))) if near else 0.0
        got_words += union * len(a)
        all_words += len(a)
        one = max((matched(norm(x["verbatim_text"])) for x in near), default=0.0)
        rec.append(union)
        single += one >= 0.9
        if union < 0.9:
            sents = pv.get("_sentences", [])
            cover: collections.Counter = collections.Counter()
            span = max(1, c["end_ms"] - c["start_ms"])
            for s, e, why in sents:
                ov = max(0, min(e, c["end_ms"]) - max(s, c["start_ms"])) if s is not None else 0
                cover[why or "teacher_clip_or_short_run"] += ov
            lost[max(cover, key=cover.get) if cover and sum(cover.values()) >= 0.5 * span else "no_transcript_overlap"] += 1
    n = len(rec)
    srt = sorted(rec)
    return {"v10_clips_in_recut_videos": n,
            "word_recovery_pct": round(100 * got_words / max(1, all_words), 1),
            "recovery_median": round(statistics.median(rec), 3) if n else None,
            "recovery_p10": round(srt[int(0.1 * n)], 3) if n else None,
            "pct_recovered_ge_0.9_union": round(100 * sum(r >= 0.9 for r in rec) / max(1, n), 1),
            "pct_recovered_ge_0.9_inside_one_v2_clip": round(100 * single / max(1, n), 1),
            "unrecovered_dominant_cause": dict(lost),
            "ceiling_note": "v10 text vs transcripts_B text alignment is median 0.956 / p10 0.76 (measured 2026-11-16), "
                            "so recovery below 1.0 is partly ASR/text difference, not lost teaching"}


def verified_share(rows: list[dict[str, Any]]) -> float:
    return round(100 * sum(r.get("speaker_verified") is True for r in rows) / max(1, len(rows)), 1)


def apply_decision(card: dict[str, Any], allow_unverified: bool) -> dict[str, Any]:
    """The criterion for building the shadow, stated in code (run on the numbers, not by eye)."""
    m, base = card["v2_recut_only"], card["v10_recut_videos"]
    checks = {
        "p95_s<=90": m["seconds"]["p95"] <= 90, "max_s<=160": m["seconds"]["max"] <= 160,
        "outside_8_60<=5%": m["pct_outside_8_60s"] <= 5, "contained<=5%": m["pct_contained"] <= 5,
        "duplicates==0": m["duplicate_text_clips"] == 0, "under_15_words==0": m["under_15_words"] == 0,
        "gate_pass>v10": m["standalone_gate_pass_pct"] > base["standalone_gate_pass_pct"],
        "schema_valid": card["validation"]["children_invalid"] == 0 and card["validation"]["parents_invalid"] == 0,
        "verified_share>=v10": card["verified_share_pct"]["v2_recut_only"] >= card["verified_share_pct"]["v10"],
    }
    ok = all(v for k, v in checks.items() if k != "verified_share>=v10") and (
        allow_unverified or checks["verified_share>=v10"])
    return {"checks": checks, "apply_ok": ok,
            "note": "verified_share check waived by --allow-unverified-shadow" if allow_unverified else ""}


def scorecard(res: dict[str, Any], allow_unverified: bool) -> dict[str, Any]:
    v2 = res["clips"]
    total = v2 + res["carried"]
    m_v1 = {}
    for cap in (60, 90):
        f = V1_DIR / f"cap{cap}" / f"scorecard_cap{cap}.json"
        m_v1[f"v1_cap{cap}"] = json.loads(f.read_text())["after"] if f.is_file() else "NOT RUN (file missing)"
    recut = {v for v, d in res["per_video"].items() if d["status"] == "recut"}
    v10_all = res["v10_children"]
    card: dict[str, Any] = {
        "schema": "resegment-v2-scorecard-v1", "date": "2026-11-16",
        "params": {"chunker_version": CHUNKER_VERSION, "corpus_version": CORPUS_VERSION,
                   "usable_min_sim": USABLE_MIN_SIM, "usable_min_aligned": USABLE_MIN_ALIGNED,
                   "absorb_max_s": ABSORB_MAX_S, "absorb_max_words": ABSORB_MAX_WORDS,
                   "max_intra_gap_ms": MAX_INTRA_GAP_MS, "ideal_s": IDEAL_S, "soft_cap_s": SOFT_CAP_S,
                   "window_s": WINDOW_S},
        "videos": {"v10": len(res["per_video"]), "recut": len(recut),
                   "carried_v10_unchanged": len(res["per_video"]) - len(recut)},
        "v10": v1.metrics(v10_all), **m_v1,
        "v2_recut_only": v1.metrics(v2), "v2_total": v1.metrics(total),
        "v10_recut_videos": v1.metrics([c for c in v10_all if c["video_id"] in recut]),
        "strict_gate_pass_pct": {"v10": round(100 * sum(gate_strict(c["verbatim_text"]) for c in v10_all) / len(v10_all), 1),
                                 "v2_recut_only": round(100 * sum(gate_strict(c["verbatim_text"]) for c in v2) / max(1, len(v2)), 1)},
        "verified_share_pct": {"v10": verified_share(v10_all), "v2_recut_only": verified_share(v2),
                               "v2_total": verified_share(total)},
        "parents": {"v10": len(res["v10_parents"]), "v2_new": len(res["parents"])},
        "short_runs_dropped": len(res["short"]), "duplicate_clips_dropped": res["dup_dropped"],
        "validation": validate_models(v2, res["parents"]),
        "v10_clips_in_carried_videos": len(res["carried"]),
        "fidelity": fidelity(v10_all, v2, res["per_video"]),
    }
    card["apply_decision"] = apply_decision(card, allow_unverified)
    return card


def write_outputs(res: dict[str, Any], card: dict[str, Any], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "proposed_clips.jsonl").open("w") as fh:  # <=10 words of text per row (repo is public)
        for c in res["clips"]:
            pid, inv4 = point_id_pair(c)
            fh.write(json.dumps({"point_id": pid, "inv4_point_id": inv4, "video_id": c["video_id"],
                                 "guru_id": c["guru_id"], "start_ms": c["start_ms"], "end_ms": c["end_ms"],
                                 "words": v1._words(c["verbatim_text"]), "parent_unit_id": c["parent_unit_id"],
                                 "speaker_verified": c["speaker_verified"], "boundary_status": c["boundary_status"],
                                 "first_10_words": " ".join(c["verbatim_text"].split()[:10]),
                                 "source_text_hash": c["source_text_hash"]}) + "\n")
    cov = {v: {k: x for k, x in d.items() if k != "_sentences"} for v, d in res["per_video"].items()}
    (out / "per_video_coverage.json").write_text(json.dumps(cov, indent=1))
    (out / "scorecard.json").write_text(json.dumps(card, indent=1))
    (out / "short_runs_dropped.jsonl").write_text("".join(json.dumps(s) + "\n" for s in res["short"]))


# ---------------------------------------------------------------- apply (guarded; NEW shadow collection only)
def apply_build(res: dict[str, Any], vec_by_id: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct

    from services.embedding_service import EmbeddingService
    from services.first_person_context_store import parent_point_id
    from services.qdrant.utils import QdrantUtils

    client = QdrantClient(url=args.qdrant_url)
    v1.create_shadow_collection(client, args.source_collection, args.target_collection)
    emb = EmbeddingService()
    done = 0
    for i in range(0, len(res["clips"]), 32):  # batch encode (v1 encoded one clip at a time)
        chunk = res["clips"][i:i + 32]
        r = emb.encode_batch([c["verbatim_text"] for c in chunk])
        pts = [PointStruct(id=point_id_pair(c)[0],
                           vector={"passage_dense": r["dense"][k],
                                   "passage_sparse": QdrantUtils.sparse_dict_to_vector(r["sparse"][k])},
                           payload={**c, "record_type": "retrieval_child"}) for k, c in enumerate(chunk)]
        client.upsert(args.target_collection, pts, wait=True)
        done += len(pts)
        print(json.dumps({"progress_clips": done, "of": len(res["clips"])}), flush=True)
    carried = [PointStruct(id=c["_id"], vector=vec_by_id[c["_id"]],
                           payload={k: v for k, v in c.items() if not k.startswith("_")}) for c in res["carried"]]
    kept_parents = {c["parent_unit_id"] for c in res["carried"]}
    par = [PointStruct(id=parent_point_id(p["parent_unit_id"]), vector={}, payload=p)
           for p in res["parents"] + [q for q in res["v10_parents"] if q["parent_unit_id"] in kept_parents]]
    for pts in (carried, par):
        for i in range(0, len(pts), 128):
            client.upsert(args.target_collection, pts[i:i + 128], wait=True)
    return {"target": args.target_collection, "children": len(res["clips"]) + len(carried), "parents": len(par),
            "approved_by": args.approved_by}


def verify_shadow(res: dict[str, Any], client: Any, target: str) -> dict[str, Any]:
    from services.first_person_context_store import point_id_for_record

    n = bad_hash = bad_id = 0
    off = None
    while True:
        recs, off = client.scroll(target, limit=500, offset=off, with_payload=True, with_vectors=False)
        for r in recs:
            p = r.payload
            if p.get("record_type") != "retrieval_child":
                continue
            n += 1
            bad_hash += v1._sha(p["verbatim_text"]) != p["source_text_hash"]
            bad_id += str(r.id) != point_id_for_record(p["source_span_id"])
        if off is None:
            break
    return {"children": n, "expected": len(res["clips"]) + len(res["carried"]), "bad_hash": bad_hash,
            "bad_point_id": bad_id}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--snapshot-confirmed", action="store_true")
    ap.add_argument("--approved-by", default="")
    ap.add_argument("--allow-unverified-shadow", action="store_true",
                    help="build even though v2 spans are speaker_verified=false (owner decision)")
    ap.add_argument("--source-collection", default="first_person_v10")
    ap.add_argument("--target-collection", default="first_person_v12_shadow")
    ap.add_argument("--qdrant-url", default="http://localhost:6333")
    ap.add_argument("--source-json", default=None)
    ap.add_argument("--data-dir", default=str(DATA))
    ap.add_argument("--only", default="", help="comma list of video ids (debug)")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)
    if args.apply:
        v1.check_apply_guards(args)
    points = v1.load_points(args.source_collection, url=args.qdrant_url, source_json=args.source_json,
                            with_vectors=args.apply)
    res = run(points, Path(args.data_dir), set(filter(None, args.only.split(","))) or None)
    card = scorecard(res, args.allow_unverified_shadow)
    write_outputs(res, card, Path(args.out))
    print(json.dumps({k: card[k] for k in ("videos", "v10", "v2_total", "strict_gate_pass_pct",
                                           "verified_share_pct", "validation", "fidelity", "apply_decision")}, indent=1))
    if args.apply:
        if not card["apply_decision"]["apply_ok"]:
            raise SystemExit("apply criterion not met; see scorecard.json apply_decision")
        vec = {p["id"]: p["vector"] for p in points}
        print(json.dumps(apply_build(res, vec, args)))
        from qdrant_client import QdrantClient

        print(json.dumps(verify_shadow(res, QdrantClient(url=args.qdrant_url), args.target_collection)))
    return 0


# ---------------------------------------------------------------- self-check
def _synthetic_words() -> list[dict[str, Any]]:
    sents = ["Anger is a signal that your inner state needs care and attention right now.",
             "When you pause and breathe you can see what the anger is protecting within you today.",
             "And so the practice is simple, you return to your breath again and again with kindness.",
             "Let us understand this."]
    out, t, i = [], 1000, 0
    for s in sents:
        for w in s.split():
            out.append({"i": i, "w": w, "s": t, "e": t + 300, "spk": "K", "al": True})
            t += 350
            i += 1
        t += 400
    out[8]["spk"] = "O"  # one noisy label inside a teacher sentence must be absorbed
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1:
        raise SystemExit(main())
    ws = _synthetic_words()
    lab, absorbed = smooth_labels(ws, {"K"})
    assert absorbed == 1 and set(lab) == {"K"}, (absorbed, set(lab))
    ss = split_sentences(ws, lab)
    assert len(ss) == 4, len(ss)
    runs, _ = teacher_runs(ss, {"K"})
    assert len(runs) == 1
    cuts = cut_run(runs[0]["sents"])
    assert cuts[0][0] == 0 and cuts[-1][1] == 3 and all(b + 1 == c[0] for (_, b), c in zip(cuts, cuts[1:])), cuts
    print("resegment_v2 self-check passed", cuts)
