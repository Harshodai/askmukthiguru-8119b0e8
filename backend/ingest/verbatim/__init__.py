"""Shared, production ingestion path for verified first-person verbatim clips.

Ports the offline pilot scripts (~/mukthiguru_attribution_data/pilot50_2026-09-25/
run_vote.py, run_speaker.py, run_clips.py, run_punct.py) into small, testable
stage functions plus one resumable orchestrator (`pipeline.run_verbatim_pipeline`).
See README.md in this directory for the stage contract.
"""
