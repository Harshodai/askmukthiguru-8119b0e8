"""Run out-of-corpus questions through /api/first-person/query and check for 0 leaks."""
import json
import sys
import time
import urllib.request

# Finite per-request timeout so one hung backend can't stall the whole run;
# a timeout lands in the same `failed` path as any other request error.
REQUEST_TIMEOUT_S = 30

OOC_QUESTIONS = [
    "What is the capital of Australia?",
    "How far is the Moon from the Earth?",
    "Who wrote the novel Pride and Prejudice?",
    "What is the population of Japan?",
    "When did World War Two end?",
    "Give me a recipe for chocolate cake",
    "What is the capital of France?",
    "How do I fix a leaking kitchen faucet?",
    "What is the speed of light in vacuum?",
    "Who won the 2022 FIFA World Cup?",
    "Explain quantum superposition in simple terms",
    "What are the main ingredients of spaghetti carbonara?",
    "How many bones are in the adult human body?",
    "What is the chemical formula for sulfuric acid?",
    "Who painted the Mona Lisa?",
    "What is the currency of Brazil?",
    "How does a four-stroke internal combustion engine work?",
    "What is the boiling point of liquid nitrogen?",
    "Who discovered penicillin?",
    "How many players are on a basketball team on court?",
    "What is the tallest mountain in North America?",
    "What year was the Eiffel Tower completed?",
    "How do I calculate the area of a circle?",
    "What is the difference between Python and JavaScript?",
    "What is the distance between New York and London?",
    "Who is the current Prime Minister of Canada?",
    "What causes solar eclipses?",
    "How many chromosomes do humans have?",
    "What is the capital of South Africa?",
    "What is Moore's Law in computing?",
    "How do airplanes generate lift?",
    "What is the atomic number of Gold?",
]

def main():
    print(f"Testing {len(OOC_QUESTIONS)} out-of-corpus questions...")
    leaks = []
    failed = []
    times = []

    for idx, q in enumerate(OOC_QUESTIONS, 1):
        payload = json.dumps({"query": q, "cache_bypass": True}).encode()
        req = urllib.request.Request(
            "http://localhost:8000/api/first-person/query",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
                data = json.loads(resp.read().decode())
            el = time.time() - t0
            times.append(el)
            status = data.get("status")
            cits = data.get("citations", [])

            if status != "abstained" or len(cits) > 0:
                print(f"[{idx}/{len(OOC_QUESTIONS)}] LEAK DETECTED! Q: {q} | status={status} | citations={len(cits)}")
                leaks.append((q, status, len(cits)))
            else:
                print(f"[{idx}/{len(OOC_QUESTIONS)}] OK (abstained in {el:.2f}s) | Q: {q}")
        except Exception as e:
            print(f"[{idx}/{len(OOC_QUESTIONS)}] ERROR: {q} -> {e}")
            failed.append((q, str(e)[:120]))
        time.sleep(0.5)

    print("=" * 60)
    print(f"Total OOC Tested: {len(OOC_QUESTIONS)}")
    print(f"Total Leaks: {len(leaks)}")
    print(f"Total Failed (not evaluated): {len(failed)}")
    for q, err in failed:
        print(f"  FAILED: {q} -> {err}")
    print(f"Leak Rate: {len(leaks)/len(OOC_QUESTIONS)*100:.1f}%")
    if times:
        print(f"Latency: min={min(times):.2f}s, avg={sum(times)/len(times):.2f}s, max={max(times):.2f}s")
    print("=" * 60)

    if leaks:
        print("FAIL: Out-of-corpus leaks found!")
        sys.exit(1)
    if failed:
        print("FAIL: some questions could not be evaluated (see FAILED lines)!")
        sys.exit(1)
    print("SUCCESS: Zero out-of-corpus leaks (100% honest abstention).")

if __name__ == "__main__":
    main()
