"""Record the English retrieval query (user_msg_en) the chat path builds for each Indic eval turn.

Run inside the backend container: scripts/ops/backend_py.sh translate_probe.py < turns on stdin as JSON lines
{"id","turn","q","lang"}; prints JSON lines {"id","turn","lang","q","user_msg_en","should_translate","error"}.
Same calls as app/orchestrator_utils.py (detect_and_prepare_language_info + _translate_cached).
"""
import asyncio
import json
import sys

from app.config import settings
from app.dependencies import get_container
from app.language_utils import detect_and_prepare_language_info
from app.orchestrator_utils import _translate_cached


async def main():
    container = get_container()
    for line in sys.stdin:
        d = json.loads(line)
        out = {k: d[k] for k in ("id", "turn", "lang", "q")}
        try:
            _, _, _, should = detect_and_prepare_language_info(container, d["q"], d["lang"])
            out["should_translate"] = bool(should)
            out["user_msg_en"] = d["q"]
            if should:
                out["user_msg_en"] = await _translate_cached(
                    container.translation, text=d["q"], source_lang=d["lang"], target_lang="en",
                    timeout=getattr(settings, "translation_timeout_s", 5.0),
                )
        except Exception as exc:  # recorded, never hidden
            out["error"] = repr(exc)[:200]
        print(json.dumps(out, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
