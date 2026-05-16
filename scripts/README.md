# scripts/

Organized by purpose following KISS/YAGNI principles.

```
scripts/
├── benchmarks/          # Performance & quality testing
│   ├── test_latency.py      # 5-phase RAG pipeline benchmark (p50/p95/p99, TTFT, concurrent, conversation flows)
│   ├── test_rag_quality.py  # RAG response quality scoring (keyword relevance, intent accuracy, citation)
│   ├── test_stt.py          # Speech-to-text benchmark
│   ├── test_e2e_ui.py       # Playwright browser E2E (chat → admin telemetry verification)
│   ├── REPORT.md            # Previous benchmark results narrative
│   └── results.json         # Machine-readable benchmark output
│
├── ingestion/           # Knowledge base data loading
│   ├── ingest_four_sacred_secrets.py
│   ├── ingest_youtube_seeds.py
│   ├── bulk_ingest_whisper.py
│   ├── smart_extract_and_ingest.py
│   ├── run_pageindex.py
│   ├── pageindex/           # PageIndex extraction utilities
│   └── ...
│
├── ops/                 # Operational utilities
│   ├── health_check.sh      # Docker service health verification
│   └── cleanup_data.py      # Data cleanup/reset
│
└── README.md            # This file
```

## Quick Start

```bash
# Run the full benchmark suite (requires Docker backend running)
pip install httpx
python3 scripts/benchmarks/test_latency.py --n 50 --concurrency 5

# Run RAG quality checks
pip install httpx rich
python3 scripts/benchmarks/test_rag_quality.py

# Run health checks
bash scripts/ops/health_check.sh
```
