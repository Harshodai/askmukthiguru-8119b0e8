import json
import os

report_path = "benchmarks/reports/ruthless_report.json"
if not os.path.exists(report_path):
    print(f"Error: {report_path} does not exist.")
    exit(1)

with open(report_path) as f:
    report = json.load(f)

print(f"Overall Production Readiness Score: {report.get('overall_score', 0):.1%}")
print(f"Verdict: {report.get('verdict')}\n")

print("Failed and Empty Response Tests:")
print("=" * 80)
count = 0
for idx, r in enumerate(report.get("results", [])):
    passed = r.get("passed")
    response = r.get("response", "")
    latency = r.get("latency_ms", 0)

    # We want to inspect why some responses are empty or failed
    if not passed or not response:
        count += 1
        print(f"Index: {idx}")
        print(f"Category: {r.get('category')}")
        print(f"Query: {r.get('query')}")
        print(f"Intent: {r.get('intent')}")
        print(f"Latency: {latency / 1000:.2f}s")
        print(f"Response: {repr(response)}")
        print(f"Cites: {r.get('citations')}")
        print(f"Passed: {passed}")
        print("-" * 80)

print(f"Total shown failures: {count}")
