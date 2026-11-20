"""Copy run jsonl files into OUTDIR with arm/rep taken from the file name (ARM_rN.jsonl) and
inline HTTP-200 crisis replies unwrapped. Raw files are never modified. Runs whose .meta has a line
starting with INVALID are skipped. Usage: normalize_runs.py OUTDIR RUN.jsonl...
"""
import json
import os
import re
import sys

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
for path in sys.argv[2:]:
    m = re.match(r"(?P<arm>.+)_r(?P<rep>\d+)\.jsonl$", os.path.basename(path))
    meta = path[: -len(".jsonl")] + ".meta"
    if os.path.exists(meta) and any(line.startswith("INVALID") for line in open(meta)):
        print("skip invalid", path)
        continue
    with open(os.path.join(out, os.path.basename(path)), "w") as f:
        for line in open(path):
            d = json.loads(line)
            d["arm"], d["rep"] = m["arm"], int(m["rep"])
            r = d["r"]
            if r.get("http") == 200 and isinstance(r.get("body"), dict):
                d["r"] = {**r["body"], "latency_s": r.get("latency_s")}
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
