"""Blind judge packet: unique (conversation context, question, served clip) pairs from run jsonl files.

Usage: judge_packet.py OUT_PACKET.jsonl OUT_INDEX.json RUN.jsonl...
The packet carries no arm, rep, flag or route data. A pair key is the question, the prior user
turns and the served citations (url + start), so the same clip for the same question gets one label
in every arm and rep. ~10% of pairs are duplicated under a new pair id for self-agreement.
"""
import hashlib
import json
import random
import sys


def clip_key(r):
    return tuple((c.get("url"), c.get("timestamp_seconds")) for c in (r.get("citations") or []))


def main():
    out_packet, out_index, *runs = sys.argv[1:]
    rows = [json.loads(line) for p in runs for line in open(p)]
    convs = {}
    for d in rows:
        convs.setdefault((d["arm"], d["rep"], d["id"]), {})[d["turn"]] = d["q"]
    pairs, index = {}, {}
    for d in rows:
        r = d["r"]
        if not r.get("citations"):
            continue
        prior = [convs[(d["arm"], d["rep"], d["id"])][t] for t in range(d["turn"])]
        key = json.dumps([prior, d["q"], clip_key(r)], ensure_ascii=False)
        pid = hashlib.sha256(key.encode()).hexdigest()[:12]
        index.setdefault(pid, []).append([d["arm"], d["rep"], d["id"], d["turn"]])
        pairs.setdefault(pid, {"pair_id": pid, "earlier_user_turns": prior, "question": d["q"],
                               "served_text": (r.get("response") or "")[:2500]})
    items = list(pairs.values())
    rng = random.Random(20261120)
    dupes = rng.sample(items, max(1, len(items) // 10))
    for p in dupes:
        q = dict(p, pair_id="r" + p["pair_id"][:11])
        index[q["pair_id"]] = [["SELF_AGREEMENT_OF", p["pair_id"]]]
        items.append(q)
    rng.shuffle(items)
    chunk = 90  # pairs per judge agent (context budget)
    for k in range(0, len(items), chunk):
        with open(f"{out_packet}.{k // chunk:02d}", "w") as f:
            for p in items[k:k + chunk]:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
    json.dump(index, open(out_index, "w"))
    print(f"pairs={len(pairs)} with_dupes={len(items)}")


if __name__ == "__main__":
    main()
