import { describe, expect, it } from "vitest";
import {
  DAG_STAGE_IDS,
  activeNodeId,
  deriveNodeStates,
  normalizeJobPhase,
  stageForDisplay,
  stageToNodeId,
} from "./ingestionStages";

describe("ingestionStages", () => {
  it("maps ECAPA speaker verification to the attribution node", () => {
    expect(stageToNodeId("speaker_verification")).toBe("stage-4-attribution");
    expect(activeNodeId({ status: "running", stage: "speaker_verification" })).toBe(
      "stage-4-attribution",
    );
  });

  it("marks earlier nodes completed and later nodes queued around the active one", () => {
    const states = deriveNodeStates({ status: "running", stage: "speaker_verification" });
    expect(states["stage-3-asr"]).toBe("completed");
    expect(states["stage-4-attribution"]).toBe("active");
    expect(states["stage-5-sanitization"]).toBe("queued");
  });

  it("accepts both backend vocabularies and any status casing", () => {
    expect(stageToNodeId("TRANSCRIBING_WHISPER")).toBe("stage-3-asr");
    expect(stageToNodeId("fetching")).toBe("stage-2-audio");
    expect(normalizeJobPhase("STARTED")).toBe("running");
    expect(normalizeJobPhase("SUCCESS")).toBe("completed");
    expect(normalizeJobPhase("Complete!")).toBe("completed");
    expect(normalizeJobPhase("FAILURE")).toBe("failed");
  });

  it("never guesses: unknown stage, idle and missing job highlight nothing", () => {
    for (const job of [
      { status: "running", stage: "some_new_stage" },
      { status: "running", stage: null },
      { status: "", stage: "indexing" },
      null,
      undefined,
    ]) {
      const states = deriveNodeStates(job);
      expect(DAG_STAGE_IDS.every((id) => states[id] === "unknown")).toBe(true);
      expect(activeNodeId(job)).toBeNull();
    }
  });

  it("marks every node completed for a finished job and none active", () => {
    const states = deriveNodeStates({ status: "completed", stage: "completed" });
    expect(DAG_STAGE_IDS.every((id) => states[id] === "completed")).toBe(true);
    expect(activeNodeId({ status: "completed" })).toBeNull();
  });

  it("marks the failing node as failed, not active", () => {
    const states = deriveNodeStates({ status: "failed", stage: "speaker_verification" });
    expect(states["stage-4-attribution"]).toBe("failed");
    expect(states["stage-2-audio"]).toBe("completed");
    expect(states["stage-8-persistence"]).toBe("queued");
    expect(activeNodeId({ status: "failed", stage: "speaker_verification" })).toBeNull();
  });

  it("keeps the last mapped stage when a first-person job fails with stage 'failed'", () => {
    expect(stageForDisplay("failed", "failed", "speaker_verification")).toBe("speaker_verification");
    const states = deriveNodeStates({
      status: "failed",
      stage: stageForDisplay("failed", "failed", "speaker_verification"),
    });
    expect(states["stage-4-attribution"]).toBe("failed");
  });

  it("leaves a mapped or running stage exactly as reported", () => {
    expect(stageForDisplay("running", "aligning", "queued")).toBe("aligning");
    expect(stageForDisplay("running", "new_stage", "aligning")).toBe("new_stage");
    expect(stageForDisplay("failed", "failed", null)).toBe("failed");
  });
});
