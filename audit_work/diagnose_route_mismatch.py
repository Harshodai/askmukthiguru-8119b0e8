import asyncio
import json

from app.orchestrator_utils import select_graph_for_query
from rag.nodes.on_device_intent import classify_with_reason

QUERIES = [
    "Compare stillness with the beautiful state and explain how they relate.",
    "How does meditation transform daily awareness over time?",
    "What is Soul Sync?",
]

async def main() -> None:
    rows = []
    for query in QUERIES:
        result = classify_with_reason(query)
        selected_none = await select_graph_for_query(query, container=None)
        selected_factual = await select_graph_for_query(
            query, container=None, detected_intent="FACTUAL", query_tier="tier2_simple"
        )
        rows.append(
            {
                "query": query,
                "on_device": result,
                "selected_without_intent": selected_none,
                "selected_with_fact_tier2": selected_factual,
            }
        )
    print(json.dumps(rows, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
