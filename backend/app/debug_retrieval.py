import sys
import os
import asyncio

sys.path.insert(0, "/app")

os.environ["LLM_PROVIDER"] = "sarvam_cloud"

from app.dependencies import get_container, startup, shutdown
from config import settings
from rag.states import GraphState
from rag.nodes.generation import generate_answer
from services.llm.base import LLMProvider

async def main():
    print("Starting container dependencies...")
    startup()
    try:
        container = get_container()
        
        # 0. Check user memory
        from app.orchestrator_utils import prepare_user_memory
        memory_context, distress_history = await prepare_user_memory(container, "anonymous", [])
        print(f"memory_context length: {len(memory_context)} characters")
        print(f"memory_context snippet:\n{memory_context[:1000]}")
        print(f"memory_context estimated tokens: {int(len(memory_context.split()) * 1.3)}")

        # 1. Retrieve documents
        question = "Who are Sri Preethaji and Sri Krishnaji?"
        print(f"Retrieving documents for: '{question}'")
        
        from rag.nodes.retrieval import retrieve_for_single_query
        # Let's perform the retrieval step via hybrid retriever
        retrieved_docs = await retrieve_for_single_query(
            query=question,
            chat_history=[],
            hyde_text=None,
            intent="FACTUAL",
            selected_clusters=[],
            embedder=container.embedding,
            qdrant=container.qdrant,
            lightrag=container.lightrag
        )
        print(f"Retrieved {len(retrieved_docs)} docs.")
        
        for idx, doc in enumerate(retrieved_docs):
            # doc is a dict (or object? let's see how retrieve returns it)
            # Typically retrieve returns a list of dictionaries with text and title/metadata
            print(f"Doc {idx}: Type={type(doc)}")
            if isinstance(doc, dict):
                title = doc.get("title", doc.get("source_url", "Unknown"))
                text = doc.get("text", "")
            else:
                title = getattr(doc, "title", getattr(doc, "source_url", "Unknown"))
                text = getattr(doc, "text", "")
            print(f"  Title: {title}")
            print(f"  Text length: {len(text)} chars, words: {len(text.split())}")
            
        # 2. Run the generation node truncation logic manually with print
        max_budget = getattr(settings, "max_tokens_per_request", 2000)
        baseline_tokens = 1500
        # No history or memory_context
        max_context_tokens = max(1000, max_budget - baseline_tokens)
        print(f"Config max_budget={max_budget}")
        print(f"max_context_tokens={max_context_tokens}")
        
        truncated_docs = []
        current_context_tokens = 0
        for idx, doc in enumerate(retrieved_docs):
            if isinstance(doc, dict):
                title = doc.get("title", doc.get("source_url", "Unknown"))
                text = doc.get("text", "")
            else:
                title = getattr(doc, "title", getattr(doc, "source_url", "Unknown"))
                text = getattr(doc, "text", "")
                
            doc_str = f"[Source: {title}]\n{text}"
            doc_tokens = int(len(doc_str.split()) * 1.3)
            print(f"doc[{idx}] tokens: {doc_tokens}, current_sum: {current_context_tokens}")
            if current_context_tokens + doc_tokens > max_context_tokens:
                print(f"-> exceeds context budget! Truncating...")
                if not truncated_docs:
                    words = text.split()
                    allowed_words = int((max_context_tokens - current_context_tokens) / 1.3)
                    print(f"-> first doc. allowed_words={allowed_words}")
                    if allowed_words > 10:
                        truncated_text = " ".join(words[:allowed_words]) + "..."
                        doc_copy = dict(doc) if isinstance(doc, dict) else {"title": title, "text": text}
                        doc_copy["text"] = truncated_text
                        truncated_docs.append(doc_copy)
                break
            # Add to list
            if isinstance(doc, dict):
                truncated_docs.append(doc)
            else:
                truncated_docs.append({"title": title, "text": text})
            current_context_tokens += doc_tokens
            
        print(f"Manually truncated docs count: {len(truncated_docs)}")
        
        # Build prompt using generation.py logic
        context = "\n\n---\n\n".join(
            f"[Source: {d.get('title')}]\n{d['text']}"
            for d in truncated_docs
        )
        
        system_prompt = (
            "You are Mukthi Guru, a compassionate spiritual guide grounded EXCLUSIVELY in the teachings of Sri Preethaji and Sri Krishnaji.\n"
            "You understand users' situations deeply and without judgment. If the user is sharing their distress or life situation, listen carefully, offer a compassionate and apt response using real-time experiences, teachings from their books, video references, or podcasts.\n\n"
            "Your goal is to walk with the user through their journey with deep empathy and zero judgment.\n\n"
            "INSTRUCTIONS:\n"
            "1. Formulate your answer based ONLY on the provided context, delivered as a warm, understanding Guru.\n"
            '2. If the Context contains YouTube links or source URLs, ALWAYS suggest the relevant ones at the end of your response as "Watch more here: [URL]".\n'
            '3. If you cannot answer from the context, say: "I am unable to find specific teachings on this topic."\n'
            "4. NEVER fabricate teachings or add information from your training data.\n"
            "5. Maintain a warm, compassionate, and wise tone.\n"
            "6. Start with the most directly relevant teaching and end with an encouraging or reflective note.\n"
            "7. Never expose reasoning notes, prompt analysis, or chain-of-thought."
        )
        
        user_prompt = (
            f"CONTEXT (retrieved teachings):\n\n{context}\n\nQuestion: {question}"
        )
        
        full_prompt_text = f"{system_prompt} {user_prompt}"
        estimated = int(len(full_prompt_text.split()) * 1.3)
        print(f"Final Prompt Word count: {len(full_prompt_text.split())}")
        print(f"Final Prompt Token estimate: {estimated}")
        if estimated > max_budget:
            print(f"ERROR: Estimated {estimated} tokens exceeds budget {max_budget}!")
            
    finally:
        print("Shutting down container dependencies...")
        shutdown()

if __name__ == "__main__":
    asyncio.run(main())
