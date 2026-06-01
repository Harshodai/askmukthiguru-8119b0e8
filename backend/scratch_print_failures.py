import json

with open("askmukthiguru_corrected_report.json") as f:
    report = json.load(f)

print(f"Overall Production Readiness Score: {report.get('production_readiness_score'):.1%}")
print(f"Verdict: {report.get('verdict')}\n")

print("Failed Tests Summary:")
print("=" * 80)
count = 0
for idx, r in enumerate(report.get("results", [])):
    if not r.get("passed") and count < 30:
        count += 1
        print(f"Index: {idx}")
        print(f"Category: {r.get('category')}")
        print(f"Query: {r.get('query')[:70]}")
        print(f"Intent: {r.get('intent')}")
        print(f"Response: {str(r.get('response'))[:200]}...")
        print(f" Cites: {r.get('citations')}")
        print(f" Passed: {r.get('passed')}")
        print("-" * 80)
