import sys
import os
import django

# Add backend directory to sys.path so we can import things
sys.path.append(os.path.abspath("backend"))

# Set environment variables so the config loads correctly
os.environ["LLM_PROVIDER"] = "sarvam_cloud"

from app.config import settings
from services.llm.base import LLMProvider

print(f"max_tokens_per_request: {settings.max_tokens_per_request}")

# Let's inspect what query is causing the issue and run the graph offline
# We can create a mock state and run the same budget logic
from rag.states import GraphState
from rag.nodes.generation import generate_answer

# Let's mock a basic state
state = {
    "question": "Who are Sri Preethaji and Sri Krishnaji?",
    "rewritten_query": "Who are Sri Preethaji and Sri Krishnaji?",
    "relevant_docs": [
        {"title": "Doc 1", "text": "Hello world " * 1000},
        {"title": "Doc 2", "text": "Test " * 2000},
        {"title": "Doc 3", "text": "Teachings " * 3000},
    ],
    "chat_history": [],
    "detected_language": "en",
    "query_tier": "fast",
}

print("Running mock generate_answer...")
try:
    import asyncio
    # Just run the truncation logic part of generate_answer
    max_budget = settings.max_tokens_per_request
    baseline_tokens = 1500
    max_context_tokens = max(1000, max_budget - baseline_tokens)
    print(f"Mock max_budget={max_budget}, max_context_tokens={max_context_tokens}")
    
    truncated_docs = []
    current_context_tokens = 0
    for idx, doc in enumerate(state["relevant_docs"]):
        doc_str = f"[Source: {doc.get('title')}]\n{doc.get('text', '')}"
        doc_tokens = int(len(doc_str.split()) * 1.3)
        print(f"doc[{idx}] tokens={doc_tokens}, current_sum={current_context_tokens}")
        if current_context_tokens + doc_tokens > max_context_tokens:
            if not truncated_docs:
                truncated_text = doc.get("text", "")
                words = truncated_text.split()
                allowed_words = int((max_context_tokens - current_context_tokens) / 1.3)
                if allowed_words > 10:
                    truncated_text = " ".join(words[:allowed_words]) + "..."
                    doc_copy = dict(doc)
                    doc_copy["text"] = truncated_text
                    truncated_docs.append(doc_copy)
            break
        truncated_docs.append(doc)
        current_context_tokens += doc_tokens
        
    print(f"Truncated docs count: {len(truncated_docs)}")
    for idx, doc in enumerate(truncated_docs):
        print(f"Truncated doc[{idx}] text length (words): {len(doc['text'].split())}")
except Exception as e:
    print(f"Error: {e}")
