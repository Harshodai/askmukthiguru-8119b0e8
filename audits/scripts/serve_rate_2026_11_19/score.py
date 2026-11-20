"""Summarize battery jsonl files: serve rate by bucket + latency. Usage: score.py b1.jsonl b2.jsonl"""
import json, sys, statistics as st
SAFETY = {"crisis_preempted", "distress", "blocked", "instant_greeting", "off_topic_domain_boundary"}
SIMPLE = {"practical", "emotion", "long", "hindi", "hinglish", "telugu", "tamil"}
b = {"simple": [], "complex": [], "multi": []}; lat = []; safety_excl = {"simple": 0, "complex": 0, "multi": 0}
for path in sys.argv[1:]:
    for line in open(path):
        d = json.loads(line); r = d["r"]
        cat = d.get("cat") or ("complex" if d["conv"].startswith("complex_") else "multi")
        if cat == "multiturn": cat = "multi"
        bucket = "simple" if cat in SIMPLE else cat if cat in b else None
        if bucket is None: continue
        rd = r.get("route_decision"); served = rd == "first_person_bridge" and bool(r.get("citations"))
        if rd in SAFETY or r.get("grounding_state") == "safety_redirect":
            safety_excl[bucket] += 1
        b[bucket].append((served, rd in SAFETY or r.get("grounding_state") == "safety_redirect", r.get("response", "")))
        if r.get("latency_s") and rd in ("first_person_bridge", "first_person_abstain"): lat.append(r["latency_s"])
for k, v in b.items():
    s = sum(x[0] for x in v); n = len(v); ns = sum(1 for x in v if not x[1])
    print(f"{k:8} served {s}/{n} raw ({s/max(n,1):.0%}); excl. safety {s}/{ns} ({s/max(ns,1):.0%})")
print(f"try-again replies: {sum(1 for v in b.values() for x in v if 'finish checking' in (x[2] or ''))}")
if lat:
    lat.sort(); print(f"latency fp turns n={len(lat)} p50={st.median(lat):.1f}s p95={lat[int(0.95*(len(lat)-1))]:.1f}s")
