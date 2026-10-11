"""Speaker-verification data fix (L-FP-HYBRID-SCAFFOLD-1).

Proves the prior probe finding is closed: ``build_store_clip`` now emits
``speaker_verified=True`` only on a real ECAPA pass, ``upsert_clips`` persists
the key, and anything else keeps the existing "shared in <channel>" label.
No teacher_id-to-display-name mapping anywhere in this path.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from unittest.mock import MagicMock

from ingest.verbatim.speaker_verify import verify_clip_speaker
from scripts.ops import build_first_person_index as bfpi
from services.attribution import resolve_attribution_label


def _speaker_result(win_lab, start=0.0, hop=1.0, ok=True) -> dict:
    return {
        "ok": ok,
        "t_centres": [start + i * hop for i in range(len(win_lab))],
        "win_lab": list(win_lab),
        "n_windows": len(win_lab),
    }


def _clip(speaker="preethaji", start=2.0, end=6.0, text="Suffering is not a fact") -> dict:
    return {
        "speaker": speaker,
        "start": start,
        "end": end,
        "verbatim_text": text,
        "transcript_hash": hashlib.sha256(text.encode()).hexdigest(),
    }


# --- predicate: real pass ----------------------------------------------------


def test_verify_passes_on_unanimous_teacher_windows():
    res = _speaker_result(["P"] * 8)
    assert verify_clip_speaker(_clip("preethaji", 2.0, 6.0), res) is True


def test_verify_passes_with_neutral_abstains_but_teacher_majority():
    res = _speaker_result(["P", "P", "P", "?", "?"])
    assert verify_clip_speaker(_clip("preethaji", 0.0, 4.0), res) is True


def test_verify_passes_for_krishnaji():
    res = _speaker_result(["K"] * 6)
    assert verify_clip_speaker(_clip("krishnaji", 1.0, 5.0), res) is True


# --- predicate: fail closed --------------------------------------------------


def test_verify_fails_on_any_host_window():
    res = _speaker_result(["P", "P", "O", "P", "P"])
    assert verify_clip_speaker(_clip("preethaji", 0.0, 4.0), res) is False


def test_verify_fails_on_competing_teacher_window():
    res = _speaker_result(["P", "P", "K", "P"])
    assert verify_clip_speaker(_clip("preethaji", 0.0, 3.0), res) is False


def test_verify_fails_when_abstains_outnumber_confirmations():
    res = _speaker_result(["P", "?", "?", "?", "?"])
    assert verify_clip_speaker(_clip("preethaji", 0.0, 4.0), res) is False


def test_verify_fails_closed_on_missing_or_bad_evidence():
    clip = _clip()
    assert verify_clip_speaker(clip, None) is False
    assert verify_clip_speaker(clip, {"ok": False}) is False
    assert verify_clip_speaker(clip, {"ok": True}) is False
    assert verify_clip_speaker(clip, {"ok": True, "t_centres": [1.0], "win_lab": []}) is False
    assert verify_clip_speaker(_clip(speaker="host"), _speaker_result(["P"] * 4)) is False
    assert verify_clip_speaker(_clip(speaker="both"), _speaker_result(["P"] * 4)) is False
    # no window overlaps the span
    assert (
        verify_clip_speaker(_clip("preethaji", 500.0, 510.0), _speaker_result(["P"] * 4)) is False
    )
    # malformed times
    assert (
        verify_clip_speaker({**clip, "start": 5.0, "end": 5.0}, _speaker_result(["P"] * 8)) is False
    )
    assert verify_clip_speaker({"speaker": "preethaji"}, _speaker_result(["P"] * 8)) is False


# --- builder: emits True only on a real pass ---------------------------------


def _store_clip(clip, speaker_result=None) -> dict:
    return bfpi.build_store_clip(
        clip,
        video_id="vidX",
        channel="Some Vlog",
        rights_cleared=False,
        layer_sha256="a" * 64,
        duration_ms=60_000,
        speaker_result=speaker_result,
    )


def test_builder_emits_verified_only_on_real_pass():
    assert _store_clip(_clip(), _speaker_result(["P"] * 8))["speaker_verified"] is True


def test_builder_omits_key_when_evidence_missing_or_failing():
    assert "speaker_verified" not in _store_clip(_clip())
    assert "speaker_verified" not in _store_clip(_clip(), None)
    assert "speaker_verified" not in _store_clip(_clip(), {"ok": False})
    failing = _speaker_result(["P", "O", "P", "P", "P"])
    assert "speaker_verified" not in _store_clip(_clip("preethaji", 0.0, 4.0), failing)


def test_builder_old_call_shape_stays_unverified():
    clip = _clip()
    out = bfpi.build_store_clip(
        clip,
        video_id="vidX",
        channel="Some Vlog",
        rights_cleared=False,
        layer_sha256="a" * 64,
        duration_ms=60_000,
    )
    assert "speaker_verified" not in out


# --- attribution: labels unchanged except on explicit True --------------------


def test_verified_clip_keeps_teacher_name_on_third_party_channel():
    assert resolve_attribution_label("Sri Krishnaji", True, "Times Now") == "Sri Krishnaji"


def test_unverified_third_party_clip_keeps_shared_in_channel():
    assert resolve_attribution_label("Sri Krishnaji", None, "Times Now") == "shared in Times Now"


# --- build_index wiring: raw speaker file -> verified clip ----------------------


def test_build_index_wires_speaker_file_to_verified_clip(tmp_path, monkeypatch):
    """End-to-end through build_index (dry-run): a passing raw/<id>_speaker.json
    yields speaker_verified_clips=1; without the file the same clip indexes
    unverified (fail-closed, key omitted)."""
    import json as _json

    monkeypatch.setattr(bfpi, "lookup_channel_metadata", lambda video_id: ("UNKNOWN", None))

    text = "Suffering is not a fact it is only a perception"
    clip = {
        "clip_id": "vidS_c0",
        "video_id": "vidS",
        "start": 1.0,
        "end": 2.0,
        "speaker": "preethaji",
        "speaker_confidence": None,
        "verbatim_text": "Suffering is not a fact",
        "display_text": "Suffering is not a fact",
        "question_context": None,
        "transcript_hash": hashlib.sha256(b"Suffering is not a fact").hexdigest(),
        "has_disputed_words": False,
        "parent_id": "vidS_p1",
    }
    base = tmp_path / "srcS"
    (base / "passages_B").mkdir(parents=True)
    (base / "transcripts_B").mkdir(parents=True)
    (base / "raw").mkdir(parents=True)
    (base / "passages_B" / "vidS.json").write_text(_json.dumps([clip]))
    (base / "transcripts_B" / "vidS.json").write_text(
        _json.dumps([{"w": w} for w in text.split(" ")])
    )
    (base / "raw" / "vidS_vote.json").write_text(_json.dumps({"ok": True, "agreement_rate": 0.95}))
    vjson = tmp_path / "videos_final.json"
    vjson.write_text(_json.dumps({"videos": [{"video_id": "vidS", "duration_s": 100.0}]}))

    def _run():
        return bfpi.build_index(
            passages_dirs=[base / "passages_B"],
            videos_json=vjson,
            report_dir=tmp_path / "report",
            collection="first_person_v1",
            apply=False,
            min_clip_duration_s=0.0,
        )

    report = _run()
    assert report["clips_indexed_total"] == 1
    assert report["speaker_verified_clips"] == 0
    assert report["videos_missing_speaker_result"] == 1

    (base / "raw" / "vidS_speaker.json").write_text(
        _json.dumps(
            {
                "ok": True,
                "t_centres": [0.0, 1.0, 2.0, 3.0],
                "win_lab": ["P", "P", "P", "P"],
                "n_windows": 4,
            }
        )
    )
    report = _run()
    assert report["clips_indexed_total"] == 1
    assert report["speaker_verified_clips"] == 1
    assert report["videos_missing_speaker_result"] == 0


# --- store: allowlist round-trip ----------------------------------------------


def _store_clip_payload(clip_text="Life is a flow of relationships.", **over) -> dict:
    from services.first_person_store import FirstPersonStore

    clip = {
        "video_id": "v1",
        "start_ms": 1000,
        "end_ms": 5000,
        "speaker": "Sri Krishnaji",
        "transcript_hash": hashlib.sha256(clip_text.encode("utf-8")).hexdigest(),
        "verbatim_text": clip_text,
        "teacher_id": "krishnaji",
        "teacher_ids": ["krishnaji"],
        "rights_cleared": True,
        **over,
    }
    client = MagicMock()

    def _retrieve(**kwargs):
        pts = client.upsert.call_args.kwargs["points"]
        wanted = set(kwargs["ids"])
        return [
            SimpleNamespace(id=str(p.id), payload=p.payload, vector=p.vector)
            for p in pts
            if str(p.id) in wanted
        ]

    client.retrieve.side_effect = _retrieve
    store = FirstPersonStore(collection="first_person_v1", client=client)
    assert store.upsert_clips([clip], passage_dense_vectors=[[0.1] * 1024]) == 1
    return client.upsert.call_args.kwargs["points"][0].payload


def test_upsert_persists_verified_key():
    assert _store_clip_payload(speaker_verified=True)["speaker_verified"] is True


def test_upsert_omits_verified_key_when_absent():
    assert "speaker_verified" not in _store_clip_payload()
