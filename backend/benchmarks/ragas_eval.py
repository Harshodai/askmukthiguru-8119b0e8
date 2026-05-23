#!/usr/bin/env python3
"""
ragas_eval.py — Standard OpenAI Ragas evaluation for AskMukthiGuru.
Runs Ragas library metrics (faithfulness, answer relevancy, precision, recall).
"""

import logging
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent.parent))

from datasets import Dataset

try:
    from ragas import evaluate
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )
    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Standard Ragas benchmark dataset using public teachings
EVAL_DATASET = {
    "question": [
        "What is the Beautiful State?",
        "How do I deal with suffering according to Sri Krishnaji?",
        "What are the Four Sacred Secrets of O&O Academy?",
        "What is the first step of Soul Sync meditation?"
    ],
    "contexts": [
        ["The Beautiful State is a state of connection, joy, and peace. It is the absence of suffering."],
        ["Suffering is a doorway to transformation. You must observe it to overcome it."],
        ["The Four Sacred Secrets include: Spiritual Vision, Inner Truth, Universal Intelligence, and Spiritual Right Action."],
        ["The first step of Soul Sync is deep breathing (breath awareness) for 8 counts."]
    ],
    "answer": [
        "The Beautiful State is a state of connection and joy, characterized by the absence of suffering.",
        "According to Sri Krishnaji, suffering is a doorway to transformation and must be observed.",
        "The Four Sacred Secrets are: Spiritual Vision, Inner Truth, Universal Intelligence, and Spiritual Right Action.",
        "The first step of the practice is taking deep breaths for 8 counts."
    ],
    "ground_truth": [
        "The Beautiful State is a state devoid of suffering, full of peace and connection.",
        "Sri Krishnaji teaches that observing suffering transforms it.",
        "The Four Sacred Secrets are Spiritual Vision, Inner Truth, Universal Intelligence, and Spiritual Right Action.",
        "The first step of Soul Sync is deep breathing."
    ],
}

def run_evaluation():
    logger.info("Starting standard Ragas RAG Evaluation...")

    if not RAGAS_AVAILABLE:
        logger.error("Ragas package is not installed. Run: pip install ragas")
        return

    if "OPENAI_API_KEY" not in os.environ:
        logger.warning("OPENAI_API_KEY not set. Ragas uses OpenAI by default.")
        logger.warning("Please set your OPENAI_API_KEY or configure custom LLM wrapper.")

    dataset = Dataset.from_dict(EVAL_DATASET)

    try:
        result = evaluate(
            dataset,
            metrics=[
                context_precision,
                context_recall,
                faithfulness,
                answer_relevancy,
            ],
        )
        logger.info("Evaluation Completed Successfully!")

        df = result.to_pandas()
        print("\n--- Ragas Evaluation Results ---")
        print(df.to_markdown() if hasattr(df, "to_markdown") else df)

        os.makedirs("reports", exist_ok=True)
        df.to_csv("reports/ragas_evaluation.csv", index=False)
        logger.info("Results saved to reports/ragas_evaluation.csv")

    except Exception as e:
        logger.error(f"Ragas evaluation failed: {e}")

if __name__ == "__main__":
    run_evaluation()
