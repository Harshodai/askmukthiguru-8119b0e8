import json
import subprocess
import sys
import time

import requests

BASE_URL = "http://localhost:8000"


def flush_redis():
    subprocess.run(
        [
            "docker",
            "exec",
            "mukthiguru-redis",
            "redis-cli",
            "-a",
            "mukthiguru_redis_pass",
            "FLUSHALL",
        ],
        capture_output=True,
    )


def get_anon_session():
    r = requests.post(f"{BASE_URL}/api/auth/anon-session")
    r.raise_for_status()
    return r.json().get("session_id")


def run_probe(session_id, question, run_id):
    headers = {"Authorization": f"Bearer {session_id}"}
    payload = {
        "messages": [],
        "user_message": question,
        "incognito": True,
        "cache_bypass": True,
        "session_id": session_id,
    }

    t0 = time.time()
    r = requests.post(f"{BASE_URL}/api/chat", json=payload, headers=headers)

    res = {}

    if r.status_code == 200:
        res = r.json()
    elif r.status_code == 202:
        data = r.json()
        job_id = data.get("job_id")
        poll_url = data.get("poll_url")
        if not poll_url:
            poll_url = f"/api/chat/poll/{job_id}"
        if poll_url.startswith("/"):
            poll_url = f"{BASE_URL}{poll_url}"

        with requests.get(poll_url, headers=headers, stream=True) as p:
            p.raise_for_status()
            for line in p.iter_lines():
                if line:
                    line = line.decode("utf-8")
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            p_data = json.loads(data_str)
                            if p_data.get("type") == "final_answer":
                                res = p_data.get("metadata", {})
                                res["response"] = p_data.get("content", "")
                            elif "result" in p_data:
                                res = p_data["result"]
                                res["response"] = res.get("answer", "")
                        except json.JSONDecodeError:
                            pass
    else:
        print(f"| {run_id} | ERROR: {r.status_code} {r.text[:100]} |")
        sys.stdout.flush()
        return "| error |"

    t1 = time.time()
    elapsed = t1 - t0

    grounding_state = res.get("grounding_state", "unknown")
    final_citations = res.get("citations", [])
    if not isinstance(final_citations, list):
        final_citations = []

    retrieval_metadata = res.get("retrieval_metadata", {})
    source_count = (
        retrieval_metadata.get("retrieved_count", 0) if isinstance(retrieval_metadata, dict) else 0
    )
    if "source_count" in res:
        source_count = res["source_count"]

    citation_urls = (
        res.get("evaluation_trace", {}).get("citation_urls", [])
        if isinstance(res.get("evaluation_trace"), dict)
        else []
    )
    if "citation_urls" in res:
        citation_urls = res["citation_urls"]

    if not isinstance(citation_urls, list):
        citation_urls = []

    answer_chars = len(res.get("response", ""))

    out = f"| {run_id} | {elapsed:.1f}s | {grounding_state} | {len(final_citations)} | {source_count} | {len(citation_urls)} -> {len(final_citations)} | {answer_chars} |"
    print(out)
    sys.stdout.flush()
    return out


def main():
    questions = [
        "What is the Beautiful State?",
        "What is Soul Sync?",
        "Suffering State vs Beautiful State?",
    ]

    with open("backend/f2_results.md", "w") as f:
        for q in questions:
            print(f"\nQuestion: {q}")
            f.write(f"\nQuestion: {q}\n")
            header1 = "| # | elapsed | grounding_state | citations | source_count | trace citation_urls -> final_citations | answer chars |"
            header2 = "| :- | ---: | :--- | ---: | ---: | :--- | ---: |"
            print(header1)
            print(header2)
            f.write(header1 + "\n")
            f.write(header2 + "\n")
            f.flush()

            flush_redis()
            try:
                session_id = get_anon_session()
            except Exception as e:
                print(f"Failed to get anon session: {e}")
                continue

            for i in range(10):
                if i > 0 and i % 4 == 0:
                    flush_redis()
                    session_id = get_anon_session()

                try:
                    out = run_probe(session_id, q, i)
                    f.write(out + "\n")
                    f.flush()
                except Exception as e:
                    err = f"| {i} | ERROR: {str(e)} |"
                    print(err)
                    f.write(err + "\n")
                    f.flush()


if __name__ == "__main__":
    main()
