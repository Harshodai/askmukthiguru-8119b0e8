import os
import argparse
import asyncio
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock test dataset
EVAL_DATASET = {
    \"question\": [
        \"What is the Beautiful State?\",
        \"How do I deal with suffering according to Sri Krishnaji?\",
    ],
    \"contexts\": [
        [\"The Beautiful State is a state of connection, joy, and peace. It is the absence of suffering.\"],
        [\"Suffering is a doorway to transformation. You must observe it to overcome it.\"],
    ],
    \"answer\": [
        \"The Beautiful State is a state of connection and joy, characterized by the absence of suffering.\",
        \"According to Sri Krishnaji, suffering is a doorway to transformation and must be observed.\",
    ],
    \"ground_truth\": [
        \"The Beautiful State is a state devoid of suffering, full of peace and connection.\",
        \"Sri Krishnaji teaches that observing suffering transforms it.\",
    ]
}

def run_evaluation():
    \"\"\"
    Run Ragas evaluation on sample data (BE-9).
    Tests for Faithfulness, Answer Relevancy, Context Precision, and Context Recall.
    \"\"\"
    logger.info(\"Starting Ragas RAG Evaluation...\")
    
    # Needs OPENAI_API_KEY for default Ragas metrics, or can be configured to use local model.
    if \"OPENAI_API_KEY\" not in os.environ:
        logger.warning(\"OPENAI_API_KEY not set. Ragas uses OpenAI by default for evaluation metrics.\")
        logger.warning(\"Please set OPENAI_API_KEY or configure Ragas to rely on the local Ollama LLM.\")
        
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
        logger.info(\"Evaluation Completed Successfully!\")
        
        # Convert to Pandas for pretty printing
        df = result.to_pandas()
        print(\"\\n--- Evaluation Results ---\")
        print(df.to_markdown())
        
        # Save to CSV
        os.makedirs(\"reports\", exist_ok=True)
        df.to_csv(\"reports/ragas_evaluation.csv\", index=False)
        logger.info(\"Results saved to reports/ragas_evaluation.csv\")
        
    except Exception as e:
        logger.error(f\"Ragas evaluation failed: {e}\")

if __name__ == \"__main__\":
    run_evaluation()
