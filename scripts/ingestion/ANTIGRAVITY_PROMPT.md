# Prompt for Antigravity — re-ingest 382 missing videos

Copy everything below into Antigravity as one prompt.

---

Run a corpus re-ingestion for the AskMukthiGuru project at
`/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8`.

**Context**: 382 YouTube videos are recorded as ingested in
`scripts/ingestion/ingestion_state.json` but have zero chunks in the live
Qdrant collection `spiritual_wisdom_contextual` (found via a production
audit). 381/382 already have cached transcripts on disk at
`scripts/ingestion/transcripts/<video_id>.md`, so this does NOT need a fresh
YouTube fetch for most of them — it just needs the ingestion pipeline
(correct transcript → audit quality → chunk → embed → write to
Qdrant/Neo4j/LightRAG) to actually run against text that's already there.
The exact list is `scripts/ingestion/missing_videos_to_reingest.txt`.

**Why this LLM setup**: correction runs on local Ollama (`qwen2.5:1.5b`,
free) — already tested and fine for that. The quality AUDIT step was tested
on the same small local model first and failed badly (misjudged real
teachings as "gibberish," 0% pass rate on a real sample) — a 1.5B model is
not reliable as a judge. Audit now routes to Sarvam Cloud instead (~₹20-25
for the whole batch; the account is already recharged and confirmed
working). This split is already wired into
`scripts/ingestion/bulk_ingest_video.py` via an `AUDIT_LLM_PROVIDER`
environment variable and already set in the launch script below — you don't
need to change any code for this.

**Steps**:

1. Check disk space first — Docker Desktop wedges and its containers stop
   responding if free space drops below ~1GB (`df -h /`). If it's low, quit
   and relaunch Docker Desktop (`osascript -e 'quit app "Docker"'` then
   `open -a Docker`, wait for `docker info` to succeed), and it's safe to run
   `docker builder prune -f && docker image prune -f` (NOT `-a`, NOT
   `--volumes` — those are safe to remove build cache/dangling images without
   touching any container data).

2. Bring the infra containers up and confirm all three report healthy:
   ```bash
   cd /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend
   docker compose up -d qdrant redis neo4j
   docker compose ps
   ```

3. Launch the ingestion (6 workers, `caffeinate` keeps the Mac from sleeping,
   `nohup` keeps it running after you disconnect):
   ```bash
   cd ~/mukthiguru-ingest-ops
   LOGFILE=~/mukthiguru-ingest-ops/reingest_full_6w_$(date +%Y%m%d_%H%M%S).log
   nohup caffeinate -i bash run_ingest.sh \
     /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/scripts/ingestion/missing_videos_to_reingest.txt \
     6 \
     "$LOGFILE" \
     "--disable-okf" \
     > "${LOGFILE}.stdout" 2>&1 &
   echo "$LOGFILE" > /tmp/current_reingest_logfile.txt
   echo "launched pid $!"
   ```

4. **Important**: `run_ingest.sh` processes ONE batch (25 videos) per
   invocation and then exits — it does not loop internally. After each batch
   finishes (watch the log for `"BATCH COMPLETED"`), you need to run step 3
   again with the SAME input file. It's checkpointed via Redis, so re-running
   is always safe — already-processed videos are skipped automatically, no
   duplicate work. Keep repeating step 3 until the log shows all 382 have
   been attempted (successes + rejects add up to 382), or write a small loop
   that reruns step 3 whenever the process exits and the batch total hasn't
   reached 382 yet.

5. Monitor progress at any point:
   ```bash
   LOGFILE=$(cat /tmp/current_reingest_logfile.txt)
   tail -f "$LOGFILE" | grep -E "✅|❌|BATCH COMPLETED"
   grep -c "✅ Success" "$LOGFILE"; grep -c "❌ Rejected\|❌ Failed" "$LOGFILE"
   ```

6. Stop cleanly if needed — safe to do anytime, resume with step 3 later:
   ```bash
   pkill -f "bulk_ingest_video"; pkill -f "run_ingest.sh"; pkill -f caffeinate
   ```

**What NOT to be alarmed by**: some videos will genuinely fail — a handful
of the 382 have near-empty real transcripts on disk (e.g. literally just
"I'm sorry" or a single word), correctly rejected by the pipeline's
deterministic pre-filter before it even reaches the LLM. That's the filter
working as intended, not a bug — don't try to force those through by
lowering thresholds. If you see a NEW failure pattern that isn't "genuinely
bad source transcript," investigate that one specifically rather than
assuming the whole run is broken.

**Already installed/fixed on this machine** — don't re-solve: `yt-dlp` (for
caption/cookie fallback), `mlx-whisper` (for local audio transcription
fallback on Apple Silicon), and the `AUDIT_LLM_PROVIDER=sarvam_cloud` +
`LLM_PROVIDER=ollama` environment wiring inside
`~/mukthiguru-ingest-ops/run_ingest.sh`.

**When fully done**: report final tallies (succeeded / rejected / total),
and note that the same audit that found this backlog also found a related
issue (~3,330 orphaned Neo4j graph nodes) that partially self-heals as more
videos get re-ingested — no separate action needed for that.
