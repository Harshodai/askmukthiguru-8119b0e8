"""Run the frozen eval set once against the local backend (or production with --live).

Usage: run_eval.py EVAL.json OUT.jsonl --arm NAME --rep N [--conc 3]
- tokens are pre-minted inside the backend container (issue_anon_session_token), so the
  5/min/IP anon-session limit does not pace the run; one fresh session per item.
- frontend request shape (history, language by script, cache_bypass for cold runs).
- a sampler thread writes `uptime` load every 30 s to OUT.load.
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import subprocess
import threading
import time
import urllib.request

BASE = os.environ.get("BATTERY_BASE", "http://localhost:8000")
DOCKER = os.path.expanduser("~/.docker/bin/docker")


def http(method, path, body=None, headers=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 method=method, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        r = urllib.request.urlopen(req, timeout=150)
        return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read()[:300].decode(errors="replace")}
    except Exception as e:  # network error is recorded, never treated as an answer
        return -1, {"error": repr(e)[:300]}


def lang_of(text):
    if re.search(r"[ऀ-ॿ]", text):
        return "hi"
    if re.search(r"[ఀ-౿]", text):
        return "te"
    if re.search(r"[஀-௿]", text):
        return "ta"
    if re.search(r"[\u0C80-\u0CFF]", text):
        return "kn"
    return "en"


def mint(n):
    # Same token format as services.auth_service.issue_anon_session_token, with only
    # app.config imported: the full service import was OOM-killed beside two backends.
    code = ("import json,hmac,hashlib,base64,secrets;from app.config import settings as s;"
            "k=s.anon_session_hmac_secret.encode();"
            "t=lambda p: p+'.'+base64.urlsafe_b64encode(hmac.new(k,p.encode(),hashlib.sha256).digest()).rstrip(b'=').decode();"
            f"print(json.dumps([t(secrets.token_urlsafe(16)) for _ in range({n})]))")
    out = subprocess.run([DOCKER, "exec", os.environ.get("MINT_CONTAINER", "mukthiguru-backend"), "python", "-c", code],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out.strip().splitlines()[-1])


_MINT_LOCK = threading.Lock()
_BREAKER = {"429": 0, "402": 0}


def mint_http():
    """Live runs: one anon token per item from POST /api/auth/anon-session (5/min/IP)."""
    with _MINT_LOCK:
        for _ in range(10):
            st, body = http("POST", "/api/auth/anon-session", {})
            if st == 200 and body.get("token"):
                time.sleep(12.5)  # stay under 5/min/IP
                return body["token"]
            time.sleep(15)
    raise SystemExit("could not mint an anonymous session")


def ask(tok, msg, hist):
    if _BREAKER["402"] or _BREAKER["429"] >= 3:
        return {"http": -2, "body": {"error": "breaker open (budget/429)"}, "latency_s": 0}
    body = {"messages": hist[-20:], "user_message": msg, "session_id": tok, "language": lang_of(msg),
            "incognito": False, "cache_bypass": True}
    t0 = time.time()
    st, job = http("POST", "/api/chat", body, {"X-Session-Id": tok})
    if st in (402, 429) or "budget" in json.dumps(job).lower():
        _BREAKER["402" if st != 429 else "429"] += 1
    if st != 202:
        return {"http": st, "body": job, "latency_s": round(time.time() - t0, 2)}
    poll_errors = 0
    for _ in range(120):
        time.sleep(1.0)
        pst, res = http("GET", job["poll_url"], None, {"X-Session-Id": tok})
        if pst != 200:  # a failed poll is an error, never an abstain (L-A-GUARD-MUST-FAIL-ON-AN-OUTAGE-1)
            poll_errors += 1
            if pst in (402, 429):
                _BREAKER["402" if pst == 402 else "429"] += 1
            if poll_errors >= 5:
                return {"http": pst, "body": res, "route_decision": "poll_error",
                        "latency_s": round(time.time() - t0, 2), "job_id": job.get("job_id")}
            time.sleep(2.0)
            continue
        if res.get("status") not in ("queued", "pending", "running", "processing"):
            r = res.get("result", res)
            r["latency_s"] = round(time.time() - t0, 2)
            r["job_id"] = job.get("job_id")
            return r
    return {"route_decision": "timeout", "latency_s": round(time.time() - t0, 2), "job_id": job.get("job_id")}


def run_item(item, tok, arm, rep):
    tok = tok or mint_http()
    hist, out = [], []
    for i, q in enumerate(item["turns"]):
        r = ask(tok, q, hist)
        out.append({"arm": arm, "rep": rep, "id": item["id"], "turn": i, "q": q, "cat": item["cat"],
                    "expect": item["expect"][i], "split": item["split"], "r": r})
        hist += [{"role": "user", "content": q}, {"role": "assistant", "content": r.get("response") or ""}]
    return out


def sampler(path, stop):
    with open(path, "a") as f:
        while not stop.is_set():
            f.write(f"{time.strftime('%H:%M:%S')} {os.getloadavg()[0]:.2f}\n")
            f.flush()
            stop.wait(30)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("eval"), ap.add_argument("out")
    ap.add_argument("--arm", required=True), ap.add_argument("--rep", type=int, required=True)
    ap.add_argument("--conc", type=int, default=3)
    ap.add_argument("--live", action="store_true", help="mint tokens over HTTP (production)")
    ap.add_argument("--per-kind", type=int, default=0, help="stratified slice: first N items per cat")
    a = ap.parse_args()
    items = json.load(open(a.eval))
    if a.per_kind:
        seen = {}
        items = [it for it in items if seen.setdefault(it["cat"], []).append(it) or len(seen[it["cat"]]) <= a.per_kind]
    toks = [None] * len(items) if a.live else mint(len(items))
    stop = threading.Event()
    threading.Thread(target=sampler, args=(a.out + ".load", stop), daemon=True).start()
    with open(a.out, "w") as f, cf.ThreadPoolExecutor(a.conc) as ex:
        for rows in ex.map(lambda p: run_item(p[0], p[1], a.arm, a.rep), zip(items, toks)):
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
    stop.set()
    if _BREAKER["402"] or _BREAKER["429"] >= 3:
        raise SystemExit(f"STOPPED: breaker opened {_BREAKER}")


if __name__ == "__main__":
    main()
