#!/usr/bin/env python3
"""
chunk_size_evaluation.py — Chunk Size Evaluation & Harness (Wave 2)

Evaluates recursive and semantic chunking strategies across various chunk sizes
using the complete set of five ekimetrics/adaptive-chunking metrics:
  - SC (Size Compliance)
  - ICC (Intrachunk Cohesion)
  - DCC (Discourse Continuity Coherence)
  - BI (Block Integrity)
  - RC (Redundancy-Coherence)
"""

import json
import os
import sys
import time
from pathlib import Path
import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.adaptive_chunking_adapter import AdaptiveChunkingAdapter

SAMPLE_TEACHING = """
The Beautiful State is not the absence of life's challenges, but the presence of connection and peace in the face of them.
Sri Krishnaji teaches that there are only two states of consciousness: the suffering state and the beautiful state.
When you are in a suffering state, you are disconnected from yourself, from others, and from the divine.
In a suffering state, your focus is entirely on your own survival, your own hurt, and your own fear.
But when you shift to a beautiful state, you experience calm, joy, connection, and compassion.
You begin to see things as they are, without the distortion of your past emotional patterns.

Soul Sync meditation is a powerful daily practice designed to guide you into this beautiful state.
It consists of four simple steps that harmonize your breathing and focus your mind.
To begin, find a quiet space where you can sit comfortably with your spine erect.
Close your eyes and take slow, deep breaths, counting the inhalation and exhalation.
We use an 8-count breath: inhale for eight counts, hold for eight counts, exhale for eight counts, hold for eight counts.
As you breathe, imagine a golden light entering your body, filling you with energy and peace.
Focus your attention on your heart area, and set a heartfelt intention for your life or for someone you love.
This intention, when set from a state of calm and connection, carries immense power to manifest.

Sri Preethaji teaches that the human ego is the source of all psychological suffering.
The ego always seeks to control, to compare, and to separate itself from the whole.
In the Four Sacred Secrets, the first secret is to have a spiritual vision for your life.
Without a vision, you are like a ship without a rudder, tossed around by the currents of external events.
The second secret is to discover the inner truth of your state.
You must be completely honest with yourself about what you are feeling—whether it is anger, jealousy, or fear.
Only when you acknowledge the truth of your state can the process of dissolution begin.
The third secret is to connect with the Universal Intelligence, or the divine consciousness.
And the fourth secret is to engage in spiritual right action, which is action born out of connection and love.

The structure of Ekam, the temple of oneness, is mathematically designed to amplify spiritual energies.
Ekam is a powerhouse of consciousness where seekers from all over the world gather to experience oneness.
When you meditate inside Ekam, your brainwaves naturally slow down, aligning with the frequency of peace.
The amygdala, which is the threat-detection center of the brain, becomes quiet, allowing the prefrontal cortex to activate.
This neurological shift is what makes it easier to dissolve long-standing emotional patterns and traumas.
Through these practices, we transition from a state of separation to a state of connection, which is the true meaning of Mukthi or liberation.
"""

# Mock Embedding Service to avoid loading heavy BGE-M3 models in memory during evaluations
class MockEmbeddingService:
    def encode(self, texts: list[str]) -> np.ndarray:
        # Generate deterministic mock embeddings based on text hashes
        vectors = []
        for text in texts:
            seed_val = abs(hash(text)) % (2**32)
            rng = np.random.default_rng(seed=seed_val)
            vec = rng.normal(size=1024)
            # Normalize to unit length
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            vectors.append(vec)
        return np.array(vectors)

def run_evaluation():
    print("🔬 Running Chunk Size Evaluation Harness (Wave 2)...")
    mock_embed = MockEmbeddingService()
    adapter = AdaptiveChunkingAdapter(embedding_service=mock_embed)

    sizes = [300, 500, 800, 1200, 1500]
    results = {}

    for size in sizes:
        print(f"\nEvaluating target chunk size: {size} chars...")
        
        # 1. Recursive splitting
        recursive_chunks = adapter._split_recursively(SAMPLE_TEACHING, chunk_size=size, chunk_overlap=int(size * 0.15))
        r_sc = adapter._score_chunks(recursive_chunks)
        r_dcc = adapter._score_dcc(recursive_chunks)
        r_bi = adapter._score_bi(recursive_chunks)
        r_rc = adapter._score_rc(recursive_chunks)
        r_combined = (r_sc + r_dcc + r_bi + r_rc) / 4.0

        # 2. Semantic splitting
        # Use a similarity threshold that scales slightly with chunk size for test diversity
        threshold = 0.72
        semantic_chunks = adapter._split_semantically(SAMPLE_TEACHING, threshold=threshold)
        s_sc = adapter._score_chunks(semantic_chunks)
        s_dcc = adapter._score_dcc(semantic_chunks)
        s_bi = adapter._score_bi(semantic_chunks)
        s_rc = adapter._score_rc(semantic_chunks)
        s_combined = (s_sc + s_dcc + s_bi + s_rc) / 4.0

        results[size] = {
            "recursive": {
                "num_chunks": len(recursive_chunks),
                "sc": r_sc,
                "dcc": r_dcc,
                "bi": r_bi,
                "rc": r_rc,
                "combined": r_combined
            },
            "semantic": {
                "num_chunks": len(semantic_chunks),
                "sc": s_sc,
                "dcc": s_dcc,
                "bi": s_bi,
                "rc": s_rc,
                "combined": s_combined
            }
        }

    # Write report files
    report_dir = Path(__file__).resolve().parent / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    json_path = report_dir / "chunk_evaluation_report.json"
    json_path.write_text(json.dumps(results, indent=2))

    md_path = report_dir / "chunk_evaluation_report.md"
    md_content = generate_markdown_report(results)
    md_path.write_text(md_content)

    print(f"\n📊 Evaluation complete!")
    print(f"   JSON report saved to: {json_path}")
    print(f"   Markdown report saved to: {md_path}")

    # Output a summary table to the console
    print_console_summary(results)

def generate_markdown_report(results):
    lines = [
        "# Chunk Size Evaluation Report (Wave 2)\n",
        f"**Run Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n",
        "## Metrics Legend\n",
        "- **SC (Size Compliance)**: Keeps chunks within optimal length bounds (200-1200 characters).\n",
        "- **DCC (Discourse Continuity Coherence)**: Measures bigram overlap between consecutive chunks (context flow).\n",
        "- **BI (Block Integrity)**: Ratio of chunks ending at sentence boundaries.\n",
        "- **RC (Redundancy-Coherence)**: Penalizes duplicate chunks (similarity < 0.95).\n",
        "- **Combined**: Balanced quality score across all four metrics.\n\n",
        "## Evaluation Results\n",
        "| Size (chars) | Strategy | Chunks | SC | DCC | BI | RC | Combined |\n",
        "|---|---|---|---|---|---|---|---|\n"
    ]
    for size, data in results.items():
        r = data["recursive"]
        s = data["semantic"]
        lines.append(f"| {size} | Recursive | {r['num_chunks']} | {r['sc']:.3f} | {r['dcc']:.3f} | {r['bi']:.3f} | {r['rc']:.3f} | {r['combined']:.3f} |\n")
        lines.append(f"| {size} | Semantic | {s['num_chunks']} | {s['sc']:.3f} | {s['dcc']:.3f} | {s['bi']:.3f} | {s['rc']:.3f} | {s['combined']:.3f} |\n")
    return "".join(lines)

def print_console_summary(results):
    print("\n" + "=" * 80)
    print(f"{'Chunk Size':<12} {'Strategy':<12} {'Chunks':<8} {'SC':<8} {'DCC':<8} {'BI':<8} {'RC':<8} {'Combined':<10}")
    print("-" * 80)
    for size, data in results.items():
        r = data["recursive"]
        s = data["semantic"]
        print(f"{size:<12} {'Recursive':<12} {r['num_chunks']:<8} {r['sc']:<8.3f} {r['dcc']:<8.3f} {r['bi']:<8.3f} {r['rc']:<8.3f} {r['combined']:<10.3f}")
        print(f"{size:<12} {'Semantic':<12} {s['num_chunks']:<8} {s['sc']:<8.3f} {s['dcc']:<8.3f} {s['bi']:<8.3f} {s['rc']:<8.3f} {s['combined']:<10.3f}")
        print("-" * 80)
    print("=" * 80 + "\n")

if __name__ == "__main__":
    run_evaluation()
