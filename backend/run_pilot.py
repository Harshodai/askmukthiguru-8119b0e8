import os, sys, json, time, logging, asyncio, resource
os.environ["REINGEST_LLM_PROVIDER"]="openrouter"
# OpenRouter only. Both the corrector and the contextualizer resolve through
# _contextualizer_service(), so REINGEST_LLM_PROVIDER already routes them; this
# pins the general provider too, so nothing in the import graph can quietly fall
# back to Ollama and burn a run on a 429 the way the 2026-08-01 attempt did.
os.environ["LLM_PROVIDER"]="openrouter"
os.environ["REINGEST_OPENROUTER_MODEL"]="google/gemma-3-12b-it"
os.environ["REINGEST_LATE_CHUNKING"]="true"
# Measured on this workload, NOT copied from the query-side number: onnx_int8
# ran encode_batch(32) at 1.07x and the whole ingest path at 0.92x — slightly
# SLOWER — because late chunking cannot use ONNX (no last_hidden_state) and is
# the larger half. ONNX INT8 remains the right choice for SERVING (44.2 ->
# 9.5 ms/query) and is safe there: with late chunking both sides mean-pool
# through torch, so the backend never touches the dense path.
os.environ["EMBEDDING_BACKEND"]="flagembedding"
os.environ["LATE_CHUNK_WINDOW_TOKENS"]="2048"
os.environ["EMBED_TORCH_THREADS"]="8"
sys.path.insert(0,'/app')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
from app.config import settings
print(f"late_chunking={settings.reingest_late_chunking} backend={settings.embedding_backend}", flush=True)
from ingest.contextual_reingest import ContextualReingestEngine
eng=ContextualReingestEngine()
t0=time.time()

# Sources may be named on the command line. `reingest(limit=N)` takes whatever
# sorts first, which is how the previous pilot spent its whole budget on two
# arbitrary sources; naming them lets a run target the ones that actually
# exercise the code under test (a clean transcript, the paginated PDF).
targets=[a for a in sys.argv[1:] if not a.startswith('-')]
if targets:
    async def _run():
        merged={"sources_processed":0,"chunks_written":0,"per_source":{},"failed":[]}
        for url in targets:
            r=await eng.reingest(source_url=url, skip_processed=False)
            merged["sources_processed"]+=r.get("sources_processed",0)
            merged["chunks_written"]+=r.get("chunks_written",0)
            merged["per_source"][url]=r
            merged["failed"].extend(r.get("failed_sources") or [])
        return merged
    res=asyncio.run(_run())
else:
    res=asyncio.run(eng.reingest(limit=2, skip_processed=True))
res["elapsed_seconds"]=round(time.time()-t0,1)
res["peak_rss_gb"]=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024*1024),2)
open('/tmp/pilot_result.json','w').write(json.dumps(res, indent=2, default=str))
print("PILOT DONE "+json.dumps({k:v for k,v in res.items() if not isinstance(v,(list,dict))}), flush=True)
