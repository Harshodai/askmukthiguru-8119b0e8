/**
 * Maps the backend's ingestion job vocabulary onto the nodes of the admin
 * ingestion DAG. Pure functions, no React, so the highlighting rules are testable.
 *
 * Two backend vocabularies exist today:
 *  - `FPJobStage` (backend/services/first_person_ingest_service.py), read from
 *    GET /api/first-person/ingest/status/{job_id}
 *  - the Celery ingest task stages ("fetching", "extracting_playlist", ...), read from
 *    GET /api/ingest/status/{task_id}
 *
 * A stage this table does not know is reported as "unknown" for every node. The DAG must
 * never guess which step is running.
 */

export const DAG_STAGE_IDS = [
  "stage-1-intake",
  "stage-2-audio",
  "stage-3-asr",
  "stage-4-attribution",
  "stage-5-sanitization",
  "stage-6-chunking",
  "stage-7-embedding",
  "stage-8-persistence",
] as const;

export type DagStageId = (typeof DAG_STAGE_IDS)[number];

export type NodeRunState = "completed" | "active" | "queued" | "failed" | "unknown";

/** Backend stage name -> the DAG node that is working while the job reports it. */
const BACKEND_STAGE_TO_NODE: Readonly<Record<string, DagStageId>> = {
  queued: "stage-1-intake",
  extracting_playlist: "stage-1-intake",
  downloading: "stage-2-audio",
  fetching: "stage-2-audio",
  transcribing_whisper: "stage-3-asr",
  transcribing_parakeet: "stage-3-asr",
  aligning: "stage-3-asr",
  speaker_verification: "stage-4-attribution",
  slicing_clips: "stage-6-chunking",
  // The pipeline reports one "indexing" stage for embedding plus the Qdrant/Memgraph
  // writes. The write is the visible tail, so the persistence node carries the pulse and
  // the embedding node counts as finished.
  indexing: "stage-8-persistence",
};

const DONE_STATUSES = new Set(["completed", "complete", "complete!", "success", "done"]);
const FAILED_STATUSES = new Set(["failed", "failure", "error"]);

export type JobPhase = "idle" | "running" | "completed" | "failed";

export function normalizeJobPhase(status: string | null | undefined): JobPhase {
  const s = (status ?? "").trim().toLowerCase();
  if (!s) return "idle";
  if (DONE_STATUSES.has(s)) return "completed";
  if (FAILED_STATUSES.has(s)) return "failed";
  return "running";
}

export function stageToNodeId(stage: string | null | undefined): DagStageId | null {
  const key = (stage ?? "").trim().toLowerCase();
  return BACKEND_STAGE_TO_NODE[key] ?? null;
}

/**
 * A failed first-person job reports `stage: "failed"`, which names no node, so the DAG
 * would lose where it broke. Callers keep the last stage that did map to a node and pass
 * it here; an unmapped stage on a running job stays as reported (never guessed).
 */
export function stageForDisplay(
  status: string | null | undefined,
  stage: string | null | undefined,
  lastKnownStage: string | null | undefined,
): string | null {
  if (stageToNodeId(stage)) return stage ?? null;
  if (normalizeJobPhase(status) === "failed") return lastKnownStage ?? stage ?? null;
  return stage ?? null;
}

export interface JobSnapshot {
  /** Raw backend status, e.g. "running", "STARTED", "failed", "SUCCESS". */
  status?: string | null;
  /** Raw backend stage, e.g. "speaker_verification". */
  stage?: string | null;
}

export function deriveNodeStates(job: JobSnapshot | null | undefined): Record<DagStageId, NodeRunState> {
  const states = {} as Record<DagStageId, NodeRunState>;
  const fill = (value: NodeRunState) => {
    for (const id of DAG_STAGE_IDS) states[id] = value;
    return states;
  };

  if (!job) return fill("unknown");
  const phase = normalizeJobPhase(job.status);
  if (phase === "idle") return fill("unknown");
  if (phase === "completed") return fill("completed");

  const current = stageToNodeId(job.stage);
  if (!current) return fill("unknown");

  const currentIndex = DAG_STAGE_IDS.indexOf(current);
  DAG_STAGE_IDS.forEach((id, index) => {
    if (index < currentIndex) states[id] = "completed";
    else if (index === currentIndex) states[id] = phase === "failed" ? "failed" : "active";
    else states[id] = "queued";
  });
  return states;
}

/** The node currently doing work, or null when no job is running or the stage is unknown. */
export function activeNodeId(job: JobSnapshot | null | undefined): DagStageId | null {
  const states = deriveNodeStates(job);
  return DAG_STAGE_IDS.find((id) => states[id] === "active") ?? null;
}
