#!/usr/bin/env python3
"""One tiny OpenRouter call to confirm usage.cost is reported for the scorer model.

Costs well under one cent. Needs OPENROUTER_API_KEY in the environment (backend/.env).
Prints the OPENROUTER_CALL_TIMING log line; look for a numeric cost, not None.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

MODEL = "anthropic/claude-haiku-5.5"


async def _main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    from services.openrouter_service import OpenRouterService

    service = OpenRouterService()
    reply = await service._call_api(
        messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        model=MODEL,
        operation="usage_cost_check",
    )
    print(f"reply length: {len(reply or '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
