"""
Mukthi Guru — Admin Telemetry Database

Provides a persistent SQLite database to store query traces,
evaluations, and user feedback. Replaces the frontend mockData.ts.
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("TELEMETRY_DB_PATH", "/app/data/telemetry.db")

async def init_telemetry_db():
    """Initialize the SQLite schema."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS chat_queries (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                anon_user_id TEXT,
                query_text TEXT,
                model TEXT,
                latency_ms INTEGER,
                status TEXT,
                created_at TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS chat_responses (
                id TEXT PRIMARY KEY,
                query_id TEXT,
                response_text TEXT,
                citations TEXT,
                faithfulness REAL,
                answer_relevancy REAL,
                context_precision REAL,
                context_recall REAL,
                hallucination_flag INTEGER,
                judge_reasoning TEXT,
                FOREIGN KEY(query_id) REFERENCES chat_queries(id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_feedbacks (
                id TEXT PRIMARY KEY,
                query_id TEXT,
                rating INTEGER,
                feedback_text TEXT,
                created_at TEXT,
                FOREIGN KEY(query_id) REFERENCES chat_queries(id)
            )
        ''')
        await db.commit()
        logger.info(f"Telemetry SQLite DB initialized at {DB_PATH}")

async def log_query_trace(query_data: dict, response_data: dict) -> None:
    """Log a complete query and response trace."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO chat_queries (id, session_id, anon_user_id, query_text, model, latency_ms, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    query_data['id'],
                    query_data.get('session_id', 'unknown'),
                    query_data.get('anon_user_id', 'unknown'),
                    query_data['query_text'],
                    query_data.get('model', 'ollama'),
                    query_data.get('latency_ms', 0),
                    query_data.get('status', 'ok'),
                    query_data['created_at']
                )
            )
            
            await db.execute(
                "INSERT INTO chat_responses (id, query_id, response_text, citations, faithfulness, answer_relevancy, context_precision, context_recall, hallucination_flag, judge_reasoning) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    response_data['id'],
                    query_data['id'],
                    response_data['response_text'],
                    json.dumps(response_data.get('citations', [])),
                    response_data.get('faithfulness', 0.0),
                    response_data.get('answer_relevancy', 0.0),
                    response_data.get('context_precision', 0.0),
                    response_data.get('context_recall', 0.0),
                    1 if response_data.get('hallucination_flag') else 0,
                    response_data.get('judge_reasoning', '')
                )
            )
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to log telemetry trace: {e}")

async def get_recent_traces(limit: int = 50) -> List[Dict[str, Any]]:
    """Fetch recent traces for Admin UI."""
    traces = []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT q.*, r.response_text, r.citations, r.faithfulness, r.hallucination_flag FROM chat_queries q LEFT JOIN chat_responses r ON q.id = r.query_id ORDER BY q.created_at DESC LIMIT ?", (limit,)) as cursor:
                async for row in cursor:
                    trace = dict(row)
                    trace['citations'] = json.loads(trace['citations']) if trace.get('citations') else []
                    trace['hallucination_flag'] = bool(trace['hallucination_flag'])
                    traces.append(trace)
    except Exception as e:
        logger.error(f"Failed to fetch traces: {e}")
    return traces
