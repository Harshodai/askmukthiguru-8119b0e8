"""Legacy v7/v8 store serving tail of the first-person pipeline (pure move).

These methods were moved verbatim out of ``services/first_person_pipeline.py``.
They run only when the context harness declines (never in the live v10-only
posture, invariant 25) and for compound questions (facet split, off while the
harness is terminal). ``FirstPersonPipeline`` inherits this mixin, so every
method keeps its name, signature, ``self`` state and call sites.

Module-level names of ``services.first_person_pipeline`` are resolved by a
function-local ``from services.first_person_pipeline import ...`` at the top of
each method. That import executes on every call, so a test that patches
``services.first_person_pipeline.<name>`` is still seen exactly as before, and
the cycle (the pipeline module imports this one to inherit it) is avoided.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from app.turn_trace import fp_note, fp_score

if TYPE_CHECKING:
    from services.first_person_pipeline import (
        FirstPersonPipelineResult,
        _ConfidenceOutcome,
        _RetrievalOutcome,
    )


class LegacyStoreServingMixin:
    """Legacy store tail (steps 3-6) and compound-question execution."""

    def _retrieve_with_answerability_gate(
        self,
        *,
        query: str,
        query_dense_vector: list[float],
        query_sparse_vector: Optional[dict[str, Any]],
        teacher_id: Optional[str],
        max_clips: int,
        retrieval_query: str,
        fp_llm_tokens: list[int],
        _ans_box: dict[str, Any],
        _ans_tokens: list[int],
        start_time: float,
    ) -> _RetrievalOutcome:
        """Step 3: retrieve candidates, with the answerability gate in flight.

        The gate and the retrieval run concurrently where the owner flags allow it,
        so a firm NO or an indeterminate verdict discards the candidates without
        spending a rerank or scorer call. A terminal verdict or a retrieval error
        is returned as ``outcome.result``; everything the serve-time gate and the
        RC-D-2 join need travels back in the other fields.
        """
        from services.first_person_pipeline import (
            _ANSWERABILITY_TIMEOUT_S,
            _ANSWERABILITY_UNSET,
            FirstPersonPipelineResult,
            _answerability_check,
            _answerability_executor,
            _async_answerability_check,
            _is_transient_connection_error,
            _RetrievalOutcome,
            logger,
            run_llm_coroutine,
            settings,
            time,
        )

        _ans_future: Optional[Any] = None

        # RC-D-2: start the question-only answerability gate in parallel with
        # retrieval. Crisis (Step 1), the topic rail, and the exact cache are
        # already past, so a redirect / blocked topic / cache hit never spends
        # this LLM call. The worker owns the single _answerability_check call;
        # the join sits before any rerank/scorer work so a firm NO skips both.
        # Capacity: the worker runs on the bounded _answerability_executor
        # (one slot per concurrent query, never a separate pool), joined at
        # the retrieval rendezvous with a bounded timeout.
        # Token accounting: the worker appends to its own _ans_tokens list;
        # the request's fp_llm_tokens is extended on the serving thread only
        # AFTER the future completes, so sum(fp_llm_tokens) never races a
        # cross-thread append. A timed-out worker's tokens are dropped, not
        # guessed.
        # Step 3: Retrieval from FirstPersonStore
        has_practice_intent = any(
            w in query.lower()
            for w in (
                "practice",
                "meditation",
                "how to",
                "technique",
                "exercise",
                "sadhana",
                "kriya",
            )
        )
        effective_max_clips = max(max_clips, 4) if has_practice_intent else max_clips

        def _search() -> list[dict[str, Any]]:
            return self._store.search_hybrid(
                query_dense_vector=query_dense_vector,
                query_sparse_vector=query_sparse_vector,
                teacher_id=teacher_id,
                limit=max(80, effective_max_clips * 16),
                # spare videos: a clip the integrity gate quarantines is backfilled
                dedup_limit=max(40, effective_max_clips * 8),
                allow_same_video_distinct_spans=has_practice_intent,
                deduplicate=False,
            )

        spec_val = getattr(settings, "first_person_speculative_parallelism_enabled", False)
        ans_val = getattr(settings, "first_person_answerability_check_enabled", False)

        def is_mock(v):
            return type(v).__name__.endswith("Mock")

        speculative_enabled = (
            spec_val is True or str(spec_val).lower() in ("true", "1")
        ) and not is_mock(spec_val)
        ans_enabled = (ans_val is True or str(ans_val).lower() in ("true", "1")) and not is_mock(
            ans_val
        )
        # A context-harness gate may already have resolved this request. This
        # snapshot is the request-local freeze: a late worker completion cannot
        # mutate the response or cause a second provider call on fallback.
        early_verdict = _ans_box.get("verdict", _ANSWERABILITY_UNSET)

        if speculative_enabled and ans_enabled and early_verdict is _ANSWERABILITY_UNSET:
            # Speculative Parallelism (Track 1):
            # Run Answerability Gate and Vector Retrieval (39ms) concurrently at t=0 using asyncio.gather.
            async def _speculative_gather():
                async def _task_ans():
                    ans_start = time.monotonic()
                    try:
                        verdict = await _async_answerability_check(
                            retrieval_query,
                            self._llm_service,
                            token_sink=_ans_tokens,
                        )
                        _ans_box["verdict"] = verdict
                    except Exception as exc:
                        logger.info(
                            "[FirstPersonPipeline] Speculative answerability error: %s",
                            type(exc).__name__,
                        )
                        _ans_box["verdict"] = None
                    finally:
                        _ans_box["duration_ms"] = (time.monotonic() - ans_start) * 1000.0
                    return _ans_box.get("verdict")

                async def _task_ret():
                    ret_start = time.monotonic()
                    try:
                        import asyncio

                        loop = asyncio.get_running_loop()
                        try:
                            res = await loop.run_in_executor(None, _search)
                        except Exception as first_error:
                            if not _is_transient_connection_error(first_error):
                                raise
                            logger.warning(
                                "[FirstPersonPipeline] Transient retrieval error, retrying once: %s",
                                first_error,
                            )
                            res = await loop.run_in_executor(None, _search)
                        return res
                    except Exception as exc:
                        logger.error("[FirstPersonPipeline] Speculative retrieval error: %s", exc)
                        raise
                    finally:
                        _ans_box["retrieval_duration_ms"] = (time.monotonic() - ret_start) * 1000.0

                import asyncio

                return await asyncio.gather(_task_ans(), _task_ret(), return_exceptions=True)

            try:
                ans_res, ret_res = run_llm_coroutine(
                    _speculative_gather,
                    timeout_s=_ANSWERABILITY_TIMEOUT_S + 2.0,
                    request_loop=self._llm_loop,
                )
                fp_llm_tokens.extend(_ans_tokens)
            except Exception as exc:
                logger.warning("[FirstPersonPipeline] Speculative gather failed: %s", exc)
                ans_res = None
                ret_res = exc

            t_retrieval_ms = float(_ans_box.get("retrieval_duration_ms", 0.0))
            # Freeze immediately after the bounded rendezvous. The speculative
            # task may be cancelled while its provider coroutine is still
            # unwinding, so never reread _ans_box after this point.
            early_verdict = ans_res if isinstance(ans_res, (bool, type(None))) else None
            _ans_box["verdict"] = early_verdict

            # If Answerability Gate returns 'no' or indeterminate:
            # immediately discard retrieval candidates and return honest abstention without calling reranker or scorer.
            if early_verdict is not True:
                latency = (time.monotonic() - start_time) * 1000.0
                stage_timings = {
                    "answerability_ms": round(float(_ans_box.get("duration_ms", 0.0)), 2),
                    "retrieval_ms": round(t_retrieval_ms, 2),
                    "integrity_ms": 0.0,
                    "rerank_ms": 0.0,
                    "scorer_ms": 0.0,
                    "assembly_ms": 0.0,
                    "total_ms": round(latency, 2),
                }
                is_no = early_verdict is False
                self._log_and_count(
                    "abstained",
                    latency,
                    0.0,
                    0,
                    0,
                    "answerability_withheld",
                    sum(fp_llm_tokens),
                )
                logger.info(
                    "[FirstPersonPipeline] Speculative answerability %s; "
                    "discarded retrieval candidates, skipped rerank/scorer",
                    "NO" if is_no else "indeterminate",
                )
                return _RetrievalOutcome(
                    result=FirstPersonPipelineResult(
                        answer_text="No verified first-person discourse found for this question.",
                        citations=[],
                        status="abstained",
                        is_direct_answer=False,
                        latency_ms=latency,
                        answerability="no" if is_no else "indeterminate",
                        abstain_reason="answerability_withheld",
                        stage_timings=stage_timings,
                    )
                )

            # If Answerability Gate returns 'yes', candidates are already pre-fetched in memory
            if isinstance(ret_res, Exception):
                latency = (time.monotonic() - start_time) * 1000.0
                stage_timings = {
                    "answerability_ms": round(float(_ans_box.get("duration_ms", 0.0)), 2),
                    "retrieval_ms": round(t_retrieval_ms, 2),
                    "integrity_ms": 0.0,
                    "rerank_ms": 0.0,
                    "scorer_ms": 0.0,
                    "assembly_ms": 0.0,
                    "total_ms": round(latency, 2),
                }
                self._log_and_count("error", latency, 0.0, 0, 0, "none", sum(fp_llm_tokens))
                return _RetrievalOutcome(
                    result=FirstPersonPipelineResult(
                        answer_text="An error occurred while retrieving first-person teachings.",
                        citations=[],
                        status="error",
                        is_direct_answer=False,
                        latency_ms=latency,
                        error=str(ret_res),
                        abstain_reason="none",
                        stage_timings=stage_timings,
                    )
                )
            raw_clips = ret_res
        else:
            if (
                bool(getattr(settings, "first_person_answerability_check_enabled", False))
                and _ans_box.get("verdict", _ANSWERABILITY_UNSET) is _ANSWERABILITY_UNSET
            ):

                def _run_answerability() -> None:
                    ans_start = time.monotonic()
                    try:
                        _ans_box["verdict"] = _answerability_check(
                            retrieval_query,
                            self._llm_service,
                            request_loop=self._llm_loop,
                            token_sink=_ans_tokens,
                        )
                    except Exception as e:
                        logger.info(
                            "[FirstPersonPipeline] Answerability background error: %s",
                            type(e).__name__,
                        )
                        _ans_box["verdict"] = None
                    finally:
                        _ans_box["duration_ms"] = (time.monotonic() - ans_start) * 1000.0

                _ans_future = _answerability_executor().submit(_run_answerability)

            t_ret_start = time.monotonic()
            try:
                try:
                    raw_clips = _search()
                except Exception as first_error:
                    if not _is_transient_connection_error(first_error):
                        raise
                    logger.warning(
                        "[FirstPersonPipeline] Transient retrieval error, retrying once: %s",
                        first_error,
                    )
                    raw_clips = _search()
            except Exception as e:
                t_retrieval_ms = (time.monotonic() - t_ret_start) * 1000.0
                logger.error(f"[FirstPersonPipeline] Hybrid retrieval failed: {e}")
                if _ans_future is not None:
                    try:
                        _ans_future.result(timeout=_ANSWERABILITY_TIMEOUT_S)
                        fp_llm_tokens.extend(_ans_tokens)
                    except TimeoutError:
                        logger.info(
                            "[FirstPersonPipeline] Answerability worker still running "
                            "after retrieval error; its tokens are dropped"
                        )
                latency = (time.monotonic() - start_time) * 1000.0
                stage_timings = {
                    "answerability_ms": round(float(_ans_box.get("duration_ms", 0.0)), 2),
                    "retrieval_ms": round(t_retrieval_ms, 2),
                    "integrity_ms": 0.0,
                    "rerank_ms": 0.0,
                    "scorer_ms": 0.0,
                    "assembly_ms": 0.0,
                    "total_ms": round(latency, 2),
                }
                self._log_and_count("error", latency, 0.0, 0, 0, "none", sum(fp_llm_tokens))
                return _RetrievalOutcome(
                    result=FirstPersonPipelineResult(
                        answer_text="An error occurred while retrieving first-person teachings.",
                        citations=[],
                        status="error",
                        is_direct_answer=False,
                        latency_ms=latency,
                        error=str(e),
                        abstain_reason="none",
                        stage_timings=stage_timings,
                    )
                )
            t_retrieval_ms = (time.monotonic() - t_ret_start) * 1000.0
        return _RetrievalOutcome(
            raw_clips=raw_clips,
            retrieval_ms=t_retrieval_ms,
            answerability_future=_ans_future,
            early_verdict=early_verdict,
            speculative_enabled=speculative_enabled,
            max_clips=effective_max_clips,
            practice_intent=has_practice_intent,
        )

    def _verify_candidates(
        self,
        *,
        raw_clips: list[dict[str, Any]],
        teacher_id: Optional[str],
        query: str,
        retrieval_query: str,
        dedup_limit: Optional[int] = None,
        allow_same_video_distinct_spans: bool = False,
    ) -> tuple[list[dict[str, Any]], int, float]:
        """Step 4: apply the serve-time gates and report what survived.

        Returns the servable clips, how many were quarantined, and the gate
        duration. The integrity, content-quality and speaker-verification checks
        fail closed; the allowlist is an intersect and the blocklist wins over it,
        so an unapproved or quarantined clip can never win a slot back.
        After all quality gates run, deduplicates per video (T4-01 / RET-01).
        """
        from services.first_person_pipeline import (
            FIRST_PERSON_QUARANTINED_TOTAL,
            _passes_content_quality_gate,
            _passes_integrity_gate,
            _quality_allowlist,
            _quality_blocklist,
            _speaker_verification,
            apply_injection_screen,
            deduplicate_clips_by_video,
            first_person_evidence_policy,
            logger,
            settings,
            time,
        )

        # Step 4: Serve-time Integrity Gate
        t_int_start = time.monotonic()
        verified_clips: list[dict[str, Any]] = []
        n_quarantined = 0
        for clip in raw_clips:
            if _passes_integrity_gate(clip, boundary_guard_enabled=self._boundary_guard_enabled):
                # ponytail: content quality gate — rejects thin clips, live-event
                # instructions, and discourse acknowledgments after integrity passes
                if _passes_content_quality_gate(
                    clip, gate_enabled=self._content_quality_gate_enabled
                ):
                    # Fail-closed invariant: unverified clips must NEVER be served to public users (UT-06)
                    if getattr(settings, "first_person_require_speaker_verified", False):
                        spk_ok, _ = _speaker_verification(clip)
                        is_verified = spk_ok or clip.get("speaker_verified") is True
                        if is_verified:
                            verified_clips.append(clip)
                        else:
                            n_quarantined += 1
                            FIRST_PERSON_QUARANTINED_TOTAL.inc()
                            logger.warning(
                                f"[FirstPersonPipeline] Clip {clip.get('point_id')} for video {clip.get('video_id')} "
                                f"rejected: speaker is not verified ({clip.get('speaker_verified')}). Quarantined."
                            )
                    else:
                        verified_clips.append(clip)
                else:
                    n_quarantined += 1
                    FIRST_PERSON_QUARANTINED_TOTAL.inc()
            else:
                n_quarantined += 1
                FIRST_PERSON_QUARANTINED_TOTAL.inc()
                logger.warning(
                    f"[FirstPersonPipeline] Clip {clip.get('point_id')} for video {clip.get('video_id')} "
                    f"failed the serve-time integrity gate. Quarantined from serving."
                )

        # A named guru is a hard scope: even if the store filter were bypassed, a clip
        # by anyone else is never substituted (L-FP-SPEAKER-REQUEST-1).
        if teacher_id and teacher_id.strip().lower() not in ("both", "all", ""):
            _want = teacher_id.strip().lower()
            verified_clips = [
                c for c in verified_clips if str(c.get("teacher_id") or "").lower() == _want
            ]

        # Quality allowlist (opt-in): serve only clips a reviewer/grader approved. Applied before reranking so
        # an unapproved clip can never win a slot; an empty/unreadable list abstains (fail closed).
        _allow = _quality_allowlist()
        if _allow is not None:
            verified_clips = [c for c in verified_clips if str(c.get("point_id")) in _allow]

        # Quality blocklist (opt-in quarantine, T-B12): a quarantined clip is
        # never served, even if allowlisted — quarantine wins. Applied AFTER
        # the allowlist intersect so a bad clip can never win a slot back. A
        # configured-but-unreadable file serves nothing (fail closed).
        _blocked = _quality_blocklist()
        if _blocked is not None:
            verified_clips = [c for c in verified_clips if str(c.get("point_id")) not in _blocked]
        elif str(getattr(settings, "first_person_quality_blocklist_path", "") or "").strip():
            verified_clips = []
        verified_clips = [
            c
            for c in verified_clips
            if first_person_evidence_policy.assess_contextual_safety(
                query,
                str(c.get("verbatim_text") or ""),
                retrieval_query=retrieval_query,
            ).may_serve
        ]
        verified_clips = apply_injection_screen(verified_clips, lane="legacy")
        if dedup_limit:
            # T4-01 (RET-01): Gate first, then dedup per video.
            verified_clips = deduplicate_clips_by_video(
                verified_clips,
                max_clips=dedup_limit,
                allow_same_video_distinct_spans=allow_same_video_distinct_spans,
            )
        t_integrity_ms = (time.monotonic() - t_int_start) * 1000.0

        return verified_clips, n_quarantined, t_integrity_ms

    def _join_answerability_gate(
        self,
        *,
        query_dense_vector: list[float],
        retrieval_query: str,
        verified_clips: list[dict[str, Any]],
        n_quarantined: int,
        t_retrieval_ms: float,
        t_integrity_ms: float,
        speculative_enabled: bool,
        early_verdict: Any,
        fp_llm_tokens: list[int],
        _ans_box: dict[str, Any],
        _ans_tokens: list[int],
        _ans_future: Optional[Any],
        start_time: float,
    ) -> tuple[Optional[FirstPersonPipelineResult], Any]:
        """RC-D-2 join: freeze the answerability verdict before any rerank or scorer.

        The speculative path already ran the gate beside retrieval, so only the
        non-speculative path joins here. A firm NO and an indeterminate verdict both
        abstain and skip the rerank/scorer pair, which is why a timeout is fixed to
        indeterminate and never reread. Returns the early result, if any, and the
        request-local verdict.
        """
        from services.first_person_pipeline import (
            _ANSWERABILITY_TIMEOUT_S,
            _ANSWERABILITY_UNSET,
            FirstPersonPipelineResult,
            _answerability_check,
            _cosine_similarity,
            logger,
            settings,
            time,
        )

        # RC-D-2 join: the background gate overlapped retrieval above. Firm NO
        # skips rerank/scorer; YES runs the full path. (Seventh review set:
        # indeterminate — timed-out/failed worker — also skips, since it
        # abstains either way; the Step 6 gate below agrees on both labels.)
        # Zero verified clips still falls through to the Step 5 reason below,
        # preserving the no_verified_clips > answerability_withheld precedence.
        if not speculative_enabled:
            early_verdict = _ans_box.get("verdict", _ANSWERABILITY_UNSET)
            if _ans_future is not None:
                # Bounded join: a hung gate worker must never stall serving. A
                # timeout leaves early_verdict None = indeterminate, the same
                # fail-toward-abstention path as a gate timeout below. Tokens
                # merge only after the future completes, so every sum() below
                # reads a serving-thread-only list.
                try:
                    _ans_future.result(timeout=_ANSWERABILITY_TIMEOUT_S)
                    fp_llm_tokens.extend(_ans_tokens)
                    early_verdict = _ans_box.get("verdict", _ANSWERABILITY_UNSET)
                except TimeoutError:
                    logger.info(
                        "[FirstPersonPipeline] Answerability join timed out; "
                        "continuing as indeterminate"
                    )
                    # The worker may still complete later, but this request's
                    # decision is already fixed to indeterminate.  Never start
                    # a second gate call and never reread the late future result.
                    early_verdict = None
                except Exception as exc:
                    logger.info(
                        "[FirstPersonPipeline] Answerability join failed; continuing as indeterminate: %s",
                        type(exc).__name__,
                    )
                    early_verdict = None
            if (
                bool(getattr(settings, "first_person_answerability_check_enabled", False))
                and early_verdict is _ANSWERABILITY_UNSET
                and _ans_future is None
            ):
                # Defensive single-call fallback: an enabled gate that was not
                # scheduled for any reason must resolve here, before rerank or
                # scorer spend.  Its result is stored as the same request-local
                # decision used below; there is no final-stage default.
                ans_start = time.monotonic()
                early_verdict = _answerability_check(
                    retrieval_query,
                    self._llm_service,
                    request_loop=self._llm_loop,
                    token_sink=fp_llm_tokens,
                )
                _ans_box["verdict"] = early_verdict
                _ans_box["duration_ms"] = (time.monotonic() - ans_start) * 1000.0
            if (
                bool(getattr(settings, "first_person_answerability_check_enabled", False))
                and early_verdict is True
            ):
                fp_note(answerability="yes")
            if (
                bool(getattr(settings, "first_person_answerability_check_enabled", False))
                and early_verdict is not True
                and verified_clips
            ):
                # Anything other than a firm YES skips rerank/scorer: a NO verdict
                # and an indeterminate (timed-out/failed gate worker) both end in
                # abstention, so spending two more LLM calls cannot change the
                # outcome. Label honestly: "no" for a firm NO, "indeterminate"
                # otherwise (the Step 6 gate below agrees on both).
                _is_firm_no = early_verdict is False
                fp_note(answerability="no" if _is_firm_no else "indeterminate")
                try:
                    early_confidence = (
                        _cosine_similarity(
                            query_dense_vector, verified_clips[0].get("passage_dense")
                        )
                        if query_dense_vector
                        else 0.0
                    )
                except Exception:  # noqa: BLE001 - logging confidence must not break serving
                    early_confidence = 0.0
                latency = (time.monotonic() - start_time) * 1000.0
                stage_timings = {
                    "answerability_ms": round(float(_ans_box.get("duration_ms", 0.0)), 2),
                    "retrieval_ms": round(t_retrieval_ms, 2),
                    "integrity_ms": round(t_integrity_ms, 2),
                    "rerank_ms": 0.0,
                    "scorer_ms": 0.0,
                    "assembly_ms": 0.0,
                    "total_ms": round(latency, 2),
                }
                self._log_and_count(
                    "abstained",
                    latency,
                    early_confidence,
                    n_quarantined,
                    0,
                    "answerability_withheld",
                    sum(fp_llm_tokens),
                )
                logger.info(
                    "[FirstPersonPipeline] Answerability %s before scoring; "
                    "skipped rerank/scorer (saved up to 2 LLM calls)",
                    "NO" if _is_firm_no else "indeterminate",
                )
                return (
                    FirstPersonPipelineResult(
                        answer_text="No verified first-person discourse found for this question.",
                        citations=[],
                        status="abstained",
                        is_direct_answer=False,
                        latency_ms=latency,
                        answerability="no" if _is_firm_no else "indeterminate",
                        abstain_reason="answerability_withheld",
                        stage_timings=stage_timings,
                    ),
                    early_verdict,
                )

        return None, early_verdict

    def _rerank_and_balance_candidates(
        self,
        *,
        retrieval_query: str,
        verified_clips: list[dict[str, Any]],
        speculative_enabled: bool,
        fp_llm_tokens: list[int],
        query_dense_vector: list[float],
        teacher_id: Optional[str],
        effective_max_clips: int,
        n_quarantined: int,
        t_retrieval_ms: float,
        t_integrity_ms: float,
        _ans_box: dict[str, Any],
        start_time: float,
        memory_signals: Optional[dict[str, Any]] = None,
    ) -> tuple[Optional[FirstPersonPipelineResult], list[dict[str, Any]], float]:
        """Steps 4b-4d: reorder, optionally LLM-rerank, then balance and truncate.

        Reorders only: the confidence below stays dense cosine (the calibration
        contract). A reranker that answers NONE implies an early abstention when the
        owner flag says so; with it off the candidates it was shown keep their
        retrieval order. Returns the early result, if any, the final candidate list
        and the combined rerank duration.
        """
        from services.first_person_pipeline import (
            FirstPersonPipelineResult,
            _apply_memory_reranking,
            _cosine_similarity,
            _llm_rerank_clips,
            logger,
            settings,
            time,
        )

        # Step 4b: optional cross-encoder reorder of the verified candidates. Reorders
        # only; confidence below stays dense cosine (the calibration contract).
        t_rerank_start = time.monotonic()
        if self._rerank_fn and len(verified_clips) >= (1 if speculative_enabled else 2):
            try:
                scores = self._rerank_fn(
                    retrieval_query, [c["verbatim_text"] for c in verified_clips]
                )
                if speculative_enabled:
                    min_rerank_score = float(
                        getattr(settings, "first_person_cross_encoder_min_score", 0.30)
                    )
                    pairs = [
                        (verified_clips[i], scores[i])
                        for i in range(len(verified_clips))
                        if scores[i] >= min_rerank_score
                    ]
                    if not pairs:
                        pairs = [(verified_clips[i], scores[i]) for i in range(len(verified_clips))]
                    pairs.sort(key=lambda p: p[1], reverse=True)
                    verified_clips = [p[0] for p in pairs]
                else:
                    order = sorted(
                        range(len(verified_clips)), key=lambda i: scores[i], reverse=True
                    )
                    verified_clips = [verified_clips[i] for i in order]
            except Exception as e:
                # ponytail: fail open to fusion order — the flag is an unproven ranking
                # tweak, and a reranker outage must not take the whole route down.
                logger.error(f"[FirstPersonPipeline] Rerank failed; keeping fusion order: {e}")

        # T6-02 (MEM-002): Apply memory signals to prioritize unseen clips for returning users.
        verified_clips = _apply_memory_reranking(verified_clips, memory_signals)

        # Step 4c: LLM reranker (selection-only, zero text generation, 2.5s budget, fallback to cosine)
        # Reranks across top candidates (up to 8) before final truncation or balancing,
        # ensuring the most relevant teaching clip is selected into top position.
        if (
            getattr(settings, "first_person_llm_rerank_enabled", True)
            and self._llm_service is not None
            and len(verified_clips) > 1
        ):
            rerank_res = _llm_rerank_clips(
                retrieval_query,
                verified_clips[:8],
                self._llm_service,
                token_sink=fp_llm_tokens,
            )
            if not rerank_res and getattr(
                settings, "first_person_rerank_none_abstain_enabled", False
            ):
                # E6c early abstention: model indicated NONE of the top candidate clips relate/answer
                t_rerank_ms = (time.monotonic() - t_rerank_start) * 1000.0
                latency = (time.monotonic() - start_time) * 1000.0
                stage_timings = {
                    "answerability_ms": round(float(_ans_box.get("duration_ms", 0.0)), 2),
                    "retrieval_ms": round(t_retrieval_ms, 2),
                    "integrity_ms": round(t_integrity_ms, 2),
                    "rerank_ms": round(t_rerank_ms, 2),
                    "scorer_ms": 0.0,
                    "assembly_ms": 0.0,
                    "total_ms": round(latency, 2),
                }
                logger.info(
                    "[FirstPersonPipeline] Reranker returned NONE; early abstaining without scorer."
                )
                self._log_and_count(
                    "abstained",
                    latency,
                    0.0,
                    n_quarantined,
                    0,
                    "relevance_below_min",
                    sum(fp_llm_tokens),
                )
                return (
                    FirstPersonPipelineResult(
                        answer_text="No verified first-person discourse found for this question.",
                        citations=[],
                        status="abstained",
                        is_direct_answer=False,
                        latency_ms=latency,
                        abstain_reason="relevance_below_min",
                        stage_timings=stage_timings,
                    ),
                    verified_clips,
                    t_rerank_ms,
                )
            # An empty reply is the reranker's NONE verdict. With the early-abstain flag
            # off it must NOT drop the candidates it was shown (rerank_res + [8:] would
            # silently discard the top 8); keep their retrieval order instead.
            verified_clips = (rerank_res or verified_clips[:8]) + verified_clips[8:]

        # Step 4d: Teacher diversity balancing when teacher_id is 'both' or None
        is_both_teachers = not teacher_id or teacher_id.lower() in ("both", "all", "")
        if is_both_teachers and len(verified_clips) > 1:
            top_clip = verified_clips[0]
            top_guru = str(top_clip.get("teacher_id") or top_clip.get("speaker") or "").lower()

            # Partition remaining candidates: any other guru vs the top clip's guru
            other_clips = [
                c
                for c in verified_clips[1:]
                if str(c.get("teacher_id") or c.get("speaker") or "").lower() != top_guru
            ]
            same_clips = [c for c in verified_clips[1:] if c not in other_clips]

            # Invariant: top-ranked match ALWAYS remains at index 0
            balanced: list[dict[str, Any]] = [top_clip]
            # ponytail: δ — plan-approved initial value (Task 1 Step B, 2026-09-29);
            # validate/fit by harness ablation, one δ only (see trace_1A.md for the
            # defect this gates: an other-teacher clip at cosine 0.5791 displaced a
            # same-teacher clip at 0.6837).
            max_cosine_gap = 0.05
            o_idx, s_idx = 0, 0
            while len(balanced) < effective_max_clips and (
                o_idx < len(other_clips) or s_idx < len(same_clips)
            ):
                # Alternate secondary slots: slot 1 gets other teacher if available, slot 2 gets same teacher, etc.
                want_other = o_idx < len(other_clips) and (
                    len(balanced) % 2 == 1 or s_idx >= len(same_clips)
                )
                if want_other and s_idx < len(same_clips):
                    # ponytail: promoting the other teacher displaces a same-teacher clip —
                    # allowed only on calibrated quality parity: candidate dense cosine must
                    # clear the fitted profile threshold (same value is_direct uses) AND the
                    # cosine gap to the displaced clip must stay within δ. No profile → no fit
                    # → never promote over a higher-cosine same-teacher clip.
                    if self._profile is not None:
                        candidate_cos = _cosine_similarity(
                            query_dense_vector, other_clips[o_idx].get("passage_dense")
                        )
                        displaced_cos = _cosine_similarity(
                            query_dense_vector, same_clips[s_idx].get("passage_dense")
                        )
                        promote_other = (
                            candidate_cos >= self._profile["threshold"]
                            and displaced_cos - candidate_cos <= max_cosine_gap
                        )
                    else:
                        promote_other = False
                    if promote_other:
                        balanced.append(other_clips[o_idx])
                        o_idx += 1
                    else:
                        balanced.append(same_clips[s_idx])
                        s_idx += 1
                elif want_other:
                    # nothing displaced (same-teacher partition exhausted) → plain append
                    balanced.append(other_clips[o_idx])
                    o_idx += 1
                else:
                    balanced.append(same_clips[s_idx])
                    s_idx += 1
            verified_clips = balanced
        else:
            verified_clips = verified_clips[:effective_max_clips]
        t_rerank_ms = (time.monotonic() - t_rerank_start) * 1000.0

        return None, verified_clips, t_rerank_ms

    def _abstain_no_verified_clips(
        self,
        *,
        verified_clips: list[dict[str, Any]],
        t_retrieval_ms: float,
        t_integrity_ms: float,
        t_rerank_ms: float,
        n_quarantined: int,
        fp_llm_tokens: list[int],
        _ans_box: dict[str, Any],
        start_time: float,
    ) -> Optional[FirstPersonPipelineResult]:
        """Step 5: the canonical zero-citation abstention when nothing survived.

        Returns None when candidates remain, so the caller continues to the
        confidence decision.
        """
        from services.first_person_pipeline import (
            FirstPersonPipelineResult,
            logger,
            time,
        )

        # Step 5: Abstention check if zero verified clips
        if not verified_clips:
            latency = (time.monotonic() - start_time) * 1000.0
            stage_timings = {
                "answerability_ms": round(float(_ans_box.get("duration_ms", 0.0)), 2),
                "retrieval_ms": round(t_retrieval_ms, 2),
                "integrity_ms": round(t_integrity_ms, 2),
                "rerank_ms": round(t_rerank_ms, 2),
                "scorer_ms": 0.0,
                "assembly_ms": 0.0,
                "total_ms": round(latency, 2),
            }
            logger.info("[FirstPersonPipeline] Zero verified clips found. Honest abstention.")
            self._log_and_count(
                "abstained", latency, 0.0, n_quarantined, 0, "no_verified_clips", sum(fp_llm_tokens)
            )
            return FirstPersonPipelineResult(
                answer_text="No verified first-person discourse found for this question.",
                citations=[],
                status="abstained",
                is_direct_answer=False,
                latency_ms=latency,
                abstain_reason="no_verified_clips",
                stage_timings=stage_timings,
            )

        return None

    def _decide_confidence(
        self,
        *,
        query: str,
        query_dense_vector: list[float],
        retrieval_query: str,
        verified_clips: list[dict[str, Any]],
        speculative_enabled: bool,
        early_verdict: Any,
        fp_llm_tokens: list[int],
        n_quarantined: int,
        t_retrieval_ms: float,
        t_integrity_ms: float,
        t_rerank_ms: float,
        _ans_box: dict[str, Any],
        start_time: float,
    ) -> _ConfidenceOutcome:
        """Step 6: score the candidates, apply the relevance gate and set confidence.

        One dense cosine per clip feeds the confidence decision, the per-clip filter
        and the citation, with no keyword boost (the profile threshold is fitted on
        raw cosine). The relevance gate scores the top candidates and abstains below
        its minimum or on an indeterminate scorer verdict; the answerability verdict
        joined earlier is reused here rather than asked again. A terminal abstention
        comes back as ``outcome.result``; the rest of the request reads the remaining
        fields.
        """
        from services.first_person_pipeline import (
            _ANSWERABILITY_UNSET,
            _BOUNDARY_INCOMPLETE,
            _RELEVANCE_INDETERMINATE,
            FirstPersonPipelineResult,
            _boundary_verdict,
            _ConfidenceOutcome,
            _cosine_similarity,
            _related_clips_for,
            _relevance_select,
            _resolve_served_directness,
            logger,
            settings,
            time,
        )

        # Step 6: Calibrated Confidence Decision
        # One cosine per clip, reused by the confidence decision, the per-clip filter and the citation.
        clip_scores = [
            _cosine_similarity(query_dense_vector, c.get("passage_dense")) for c in verified_clips
        ]

        # No keyword boost: the profile threshold is fitted on raw dense cosine
        # (invariant 3). A topic word in the QUESTION says nothing about whether
        # the CLIP answers it, and +0.1 on the score would let a fitted profile
        # promote a topic match to "direct answer" (removed 2026-10-05).

        # Relevance gate (2026-10-11): the answerability gate only reads the QUESTION, so an
        # in-domain question was always served its top clip whatever that clip said. Score
        # (question, clip) for the top candidates and serve the best >= min score, else abstain.
        t_scorer_start = time.monotonic()
        second_clip: Optional[dict[str, Any]] = None
        second_score = 0.0
        judge_meta: dict[str, Any] = {}
        # Relevance score of the clip that will actually be served. None when the gate is
        # off/indeterminate; a 2 then keeps the answer related, never direct.
        _pick_relevance_score: Optional[int] = None
        if getattr(settings, "first_person_relevance_gate_enabled", True):
            candidates = verified_clips[:3]
            rel_scores: list[int] = []
            from services import first_person_judge

            if first_person_judge.judge_active():
                pick = _relevance_select(
                    retrieval_query or query,
                    candidates,
                    self._llm_service,
                    self._llm_loop,
                    token_sink=fp_llm_tokens,
                    scores_out=rel_scores,
                    judge_meta_out=judge_meta,
                )
            elif speculative_enabled and candidates:
                min_rel = int(getattr(settings, "first_person_relevance_min_score", 3))
                # Cascade Reranker-to-Scorer Filtering (Track 1):
                # Only score candidate #1 first. If candidate #1 passes with score >= min_rel,
                # serve it immediately. Only evaluate candidate #2 on tie/rejection.
                scores_c1: list[int] = []
                pick_c1 = _relevance_select(
                    retrieval_query or query,
                    [candidates[0]],
                    self._llm_service,
                    self._llm_loop,
                    token_sink=fp_llm_tokens,
                    scores_out=scores_c1,
                )
                if pick_c1 == 0 and scores_c1 and scores_c1[0] >= min_rel:
                    pick = 0
                    rel_scores = scores_c1
                elif pick_c1 == _RELEVANCE_INDETERMINATE:
                    pick = _RELEVANCE_INDETERMINATE
                    rel_scores = []
                elif len(candidates) > 1:
                    # Clips 2 and 3 are scored together in one call, so the third
                    # candidate is no longer silently dropped (audit 2026-10-25;
                    # review R5) and the worst case is still two scorer calls.
                    scores_rest: list[int] = []
                    pick_rest = _relevance_select(
                        retrieval_query or query,
                        candidates[1:],
                        self._llm_service,
                        self._llm_loop,
                        token_sink=fp_llm_tokens,
                        scores_out=scores_rest,
                    )
                    if pick_rest == _RELEVANCE_INDETERMINATE:
                        pick = _RELEVANCE_INDETERMINATE
                        rel_scores = []
                    elif pick_rest is not None and scores_rest:
                        pick = 1 + pick_rest
                        rel_scores = [scores_c1[0] if scores_c1 else 0, *scores_rest]
                    else:
                        pick = None
                        rel_scores = [scores_c1[0] if scores_c1 else 0, *scores_rest]
                else:
                    pick = None
                    rel_scores = scores_c1
            else:
                pick = _relevance_select(
                    retrieval_query or query,
                    candidates,
                    self._llm_service,
                    self._llm_loop,
                    token_sink=fp_llm_tokens,
                    scores_out=rel_scores,
                )
            for _trace_score in rel_scores:
                fp_score(_trace_score)
            fp_note(min_score=int(getattr(settings, "first_person_relevance_min_score", 3)))
            if pick is None or pick == _RELEVANCE_INDETERMINATE:
                t_scorer_ms = (time.monotonic() - t_scorer_start) * 1000.0
                latency = (time.monotonic() - start_time) * 1000.0
                abstain_answerability = (
                    "relevance_indeterminate" if pick is not None else "relevance_below_min"
                )
                stage_timings = {
                    "answerability_ms": round(float(_ans_box.get("duration_ms", 0.0)), 2),
                    "retrieval_ms": round(t_retrieval_ms, 2),
                    "integrity_ms": round(t_integrity_ms, 2),
                    "rerank_ms": round(t_rerank_ms, 2),
                    "scorer_ms": round(t_scorer_ms, 2),
                    "assembly_ms": 0.0,
                    "total_ms": round(latency, 2),
                }
                self._log_and_count(
                    "abstained",
                    latency,
                    clip_scores[0],
                    n_quarantined,
                    0,
                    abstain_answerability,
                    sum(fp_llm_tokens),
                )
                return _ConfidenceOutcome(
                    result=FirstPersonPipelineResult(
                        answer_text="No verified first-person discourse found for this question.",
                        citations=[],
                        status="abstained",
                        is_direct_answer=False,
                        latency_ms=latency,
                        answerability=abstain_answerability,
                        abstain_reason=abstain_answerability,
                        stage_timings=stage_timings,
                        # A25: the candidates are integrity-verified; they simply did
                        # not reach the relevance minimum, so they are offered as
                        # explicitly related, not-answer clips (flag-gated). Indeterminate
                        # is a scorer failure, not a below-min verdict — offer nothing there.
                        related_clips=(
                            _related_clips_for(verified_clips, clip_scores) if pick is None else []
                        ),
                    )
                )
            if getattr(settings, "first_person_second_quote_enabled", False) and len(
                rel_scores
            ) == len(candidates):
                minimum = int(getattr(settings, "first_person_relevance_min_score", 3))
                others = [
                    i
                    for i in range(len(candidates))
                    if i != pick
                    and rel_scores[i] >= minimum
                    and candidates[i].get("video_id") != candidates[pick].get("video_id")
                ]
                if others:
                    best_other = max(others, key=lambda i: (rel_scores[i], -i))
                    second_clip, second_score = candidates[best_other], clip_scores[best_other]
            if pick != 0:
                verified_clips = [verified_clips[pick]] + [
                    c for i, c in enumerate(verified_clips) if i != pick
                ]
                clip_scores = [clip_scores[pick]] + [
                    s for i, s in enumerate(clip_scores) if i != pick
                ]
            if isinstance(pick, int) and 0 <= pick < len(rel_scores):
                _pick_relevance_score = int(rel_scores[pick])
        t_scorer_ms = (time.monotonic() - t_scorer_start) * 1000.0

        top_clip = verified_clips[0]
        confidence = clip_scores[0]
        is_direct = self._profile is not None and confidence >= self._profile["threshold"]

        judge_editorial_set: Optional[dict[str, Any]] = None
        if judge_meta and judge_meta.get("editorial_set"):
            judge_editorial_set = dict(judge_meta["editorial_set"])
            if judge_editorial_set.get("status") == "supported":
                is_direct = True
        elif judge_meta and judge_meta.get("selected") is not None:
            _j_scores = judge_meta.get("scores", [])
            _j_sel = judge_meta.get("selected")
            if isinstance(_j_sel, int) and 0 <= _j_sel < len(_j_scores):
                _j_item = _j_scores[_j_sel]
                _min_rel = int(getattr(settings, "first_person_relevance_min_score", 3))
                _answers = bool(_j_item.get("answers", False))
                _rel = int(_j_item.get("relevance", 0))
                _is_direct_judge = _answers and _rel >= _min_rel
                judge_editorial_set = {
                    "status": "supported" if _is_direct_judge else "partial",
                    "primary_intent": "general",
                    "candidate_facets": ["general"],
                    "facet_coverage": {"general": "direct" if _is_direct_judge else "indirect"},
                    "reasons": [
                        "judge_verified_direct" if _is_direct_judge else "judge_related_only"
                    ],
                }
                if _is_direct_judge:
                    is_direct = True

        # A clip whose persisted evidence says it does not terminate on real
        # terminal punctuation is answerable but not a whole-thought teaching:
        # serve it as related, never as a direct answer. (Owner decision
        # 2026-10-10 kept these clips in the corpus; it did not call them direct.)
        # Before that, honour the relevance band: the judge/calibration may only grant
        # directness for a clip the scorer placed at 3 (serving invariant #1 / WS3).
        is_direct = _resolve_served_directness(is_direct, _pick_relevance_score)
        if is_direct and any(
            _boundary_verdict(clip)[0] == _BOUNDARY_INCOMPLETE for clip in verified_clips
        ):
            logger.info(
                "[FirstPersonPipeline] Top clip has incomplete persisted boundary evidence; "
                "serving as related, not direct."
            )
            is_direct = False

        # Phase 2 (2026-09-30): answerability gate. Audit B served 3/3
        # out-of-corpus questions as direct answers (top-1 cosine 0.48-0.65 vs the
        # 0.45 threshold), so cosine alone cannot enforce the abstention contract.
        # An LLM classifies the QUESTION only (YES/NO, never answers it) before
        # is_direct=True is committed. Anything but YES — NO, timeout, provider
        # error, degraded/canned output, unparseable output, no llm_service —
        # fails toward the existing honest abstention shape (zero citations).
        # Gated by first_person_answerability_check_enabled (kill-switch: flag off
        # = exact pre-change behavior, no LLM call, byte-compatible cache keys).
        answerability: Optional[str] = None
        # 2026-10-11: the gate must cover EVERY clip about to be served, not only
        # is_direct ones. With no calibration profile is_direct is always False, so
        # the weak_match ("Related, not a direct answer") path skipped the gate and
        # served 'capital of France' a leadership quote and 'bake a cake' an
        # 'addicted to chocolate' quote (live, 2026-10-11).
        if bool(getattr(settings, "first_person_answerability_check_enabled", False)):
            # RC-D-2: the verdict was already joined before rerank above; reuse
            # it so the gate costs exactly one LLM call. Any unset state should
            # have been resolved before rerank/scorer above; keep a defensive
            # indeterminate mapping here rather than ever defaulting to YES.
            verdict = None if early_verdict is _ANSWERABILITY_UNSET else early_verdict
            answerability = {True: "yes", False: "no"}.get(verdict, "indeterminate")
            fp_note(answerability=answerability)
            logger.info(
                "[FirstPersonPipeline] Answerability verdict=%s direct_served=%s",
                answerability,
                verdict is True,
            )
            if verdict is not True:
                latency = (time.monotonic() - start_time) * 1000.0
                stage_timings = {
                    "answerability_ms": round(float(_ans_box.get("duration_ms", 0.0)), 2),
                    "retrieval_ms": round(t_retrieval_ms, 2),
                    "integrity_ms": round(t_integrity_ms, 2),
                    "rerank_ms": round(t_rerank_ms, 2),
                    "scorer_ms": round(t_scorer_ms, 2),
                    "assembly_ms": 0.0,
                    "total_ms": round(latency, 2),
                }
                self._log_and_count(
                    "abstained",
                    latency,
                    confidence,
                    n_quarantined,
                    0,
                    "answerability_withheld",
                    sum(fp_llm_tokens),
                )
                return _ConfidenceOutcome(
                    result=FirstPersonPipelineResult(
                        answer_text="No verified first-person discourse found for this question.",
                        citations=[],
                        status="abstained",
                        is_direct_answer=False,
                        latency_ms=latency,
                        answerability=answerability,
                        abstain_reason="answerability_withheld",
                        stage_timings=stage_timings,
                    )
                )

        return _ConfidenceOutcome(
            verified_clips=verified_clips,
            clip_scores=clip_scores,
            second_clip=second_clip,
            second_score=second_score,
            scorer_ms=t_scorer_ms,
            top_clip=top_clip,
            confidence=confidence,
            is_direct=is_direct,
            answerability=answerability,
            editorial_set=judge_editorial_set,
        )

    def _serve_from_legacy_store(
        self,
        *,
        query: str,
        query_dense_vector: list[float],
        query_sparse_vector: Optional[dict[str, Any]],
        teacher_id: Optional[str],
        max_clips: int,
        retrieval_query: str,
        language: str,
        cache_bypass: bool,
        request_allow_state: str,
        request_block_state: str,
        fp_llm_tokens: list[int],
        _ans_box: dict[str, Any],
        start_time: float,
        memory_signals: Optional[dict[str, Any]],
    ) -> FirstPersonPipelineResult:
        """Steps 3-6 and assembly over the legacy FirstPersonStore (sync)."""
        _ans_tokens: list[int] = []
        t_retrieval_ms = 0.0
        t_integrity_ms = 0.0
        t_rerank_ms = 0.0
        t_scorer_ms = 0.0

        # Step 3: retrieval from FirstPersonStore with the RC-D-2 question-only
        # answerability gate in flight. A terminal gate verdict or a retrieval
        # error comes back as outcome.result and is served as-is.
        outcome = self._retrieve_with_answerability_gate(
            query=query,
            query_dense_vector=query_dense_vector,
            query_sparse_vector=query_sparse_vector,
            teacher_id=teacher_id,
            max_clips=max_clips,
            retrieval_query=retrieval_query,
            fp_llm_tokens=fp_llm_tokens,
            _ans_box=_ans_box,
            _ans_tokens=_ans_tokens,
            start_time=start_time,
        )
        if outcome.result is not None:
            return outcome.result
        raw_clips = outcome.raw_clips
        t_retrieval_ms = outcome.retrieval_ms
        fp_note(n_retrieved=len(raw_clips or ()), retrieval_ms=round(t_retrieval_ms, 1))
        _ans_future = outcome.answerability_future
        early_verdict = outcome.early_verdict
        speculative_enabled = outcome.speculative_enabled
        effective_max_clips = outcome.max_clips
        has_practice_intent = outcome.practice_intent

        # Step 4: serve-time integrity gate, then the allowlist/blocklist quarantine,
        # then per-video deduplication (T4-01 / RET-01).
        verified_clips, n_quarantined, t_integrity_ms = self._verify_candidates(
            raw_clips=raw_clips,
            teacher_id=teacher_id,
            query=query,
            retrieval_query=retrieval_query,
            dedup_limit=max(40, effective_max_clips * 8),
            allow_same_video_distinct_spans=has_practice_intent,
        )

        # Served text is the stored verbatim_text, byte for byte (invariants 2
        # and 13). An earlier serve-time pass rewrote verbatim_text with the ASR
        # cleaner and recomputed transcript_hash AFTER the integrity gate, and
        # stamped hand-written titles, "discourse_context" and speaker labels onto
        # clips. That served words the store does not hold and metadata nobody
        # stored. Cleaning belongs at ingest (build_first_person_index,
        # FirstPersonStore.upsert_clips), where the hash is written with it.
        # Pinned by tests/test_fp_serves_stored_text_2026_10_06.py.

        # RC-D-2 join: freeze the answerability verdict before rerank or scorer.
        join_result, early_verdict = self._join_answerability_gate(
            query_dense_vector=query_dense_vector,
            retrieval_query=retrieval_query,
            verified_clips=verified_clips,
            n_quarantined=n_quarantined,
            t_retrieval_ms=t_retrieval_ms,
            t_integrity_ms=t_integrity_ms,
            speculative_enabled=speculative_enabled,
            early_verdict=early_verdict,
            fp_llm_tokens=fp_llm_tokens,
            _ans_box=_ans_box,
            _ans_tokens=_ans_tokens,
            _ans_future=_ans_future,
            start_time=start_time,
        )
        if join_result is not None:
            return join_result

        # Steps 4b-4d: reorder, optionally LLM-rerank, then balance and truncate.
        rerank_result, verified_clips, t_rerank_ms = self._rerank_and_balance_candidates(
            retrieval_query=retrieval_query,
            verified_clips=verified_clips,
            speculative_enabled=speculative_enabled,
            fp_llm_tokens=fp_llm_tokens,
            query_dense_vector=query_dense_vector,
            teacher_id=teacher_id,
            effective_max_clips=effective_max_clips,
            n_quarantined=n_quarantined,
            t_retrieval_ms=t_retrieval_ms,
            t_integrity_ms=t_integrity_ms,
            _ans_box=_ans_box,
            start_time=start_time,
            memory_signals=memory_signals,
        )
        if rerank_result is not None:
            return rerank_result

        # Step 5: abstain honestly when no candidate survived the gates.
        empty_result = self._abstain_no_verified_clips(
            verified_clips=verified_clips,
            t_retrieval_ms=t_retrieval_ms,
            t_integrity_ms=t_integrity_ms,
            t_rerank_ms=t_rerank_ms,
            n_quarantined=n_quarantined,
            fp_llm_tokens=fp_llm_tokens,
            _ans_box=_ans_box,
            start_time=start_time,
        )
        if empty_result is not None:
            return empty_result

        # Step 6: calibrated confidence, with the relevance gate and the
        # already-joined answerability verdict deciding directness.
        confidence_outcome = self._decide_confidence(
            query=query,
            query_dense_vector=query_dense_vector,
            retrieval_query=retrieval_query,
            verified_clips=verified_clips,
            speculative_enabled=speculative_enabled,
            early_verdict=early_verdict,
            fp_llm_tokens=fp_llm_tokens,
            n_quarantined=n_quarantined,
            t_retrieval_ms=t_retrieval_ms,
            t_integrity_ms=t_integrity_ms,
            t_rerank_ms=t_rerank_ms,
            _ans_box=_ans_box,
            start_time=start_time,
        )
        if confidence_outcome.result is not None:
            return confidence_outcome.result
        verified_clips = confidence_outcome.verified_clips
        clip_scores = confidence_outcome.clip_scores
        second_clip = confidence_outcome.second_clip
        second_score = confidence_outcome.second_score
        t_scorer_ms = confidence_outcome.scorer_ms
        top_clip = confidence_outcome.top_clip
        confidence = confidence_outcome.confidence
        is_direct = confidence_outcome.is_direct
        answerability = confidence_outcome.answerability
        editorial_set = confidence_outcome.editorial_set

        # Assembly: citations, clip metadata, the exact-cache write and the metrics.
        return self._assemble_result(
            query=query,
            query_dense_vector=query_dense_vector,
            language=language,
            teacher_id=teacher_id,
            cache_bypass=cache_bypass,
            request_allow_state=request_allow_state,
            request_block_state=request_block_state,
            verified_clips=verified_clips,
            clip_scores=clip_scores,
            top_clip=top_clip,
            second_clip=second_clip,
            second_score=second_score,
            confidence=confidence,
            is_direct=is_direct,
            answerability=answerability,
            has_practice_intent=has_practice_intent,
            n_quarantined=n_quarantined,
            fp_llm_tokens=fp_llm_tokens,
            _ans_box=_ans_box,
            t_retrieval_ms=t_retrieval_ms,
            t_integrity_ms=t_integrity_ms,
            t_rerank_ms=t_rerank_ms,
            t_scorer_ms=t_scorer_ms,
            start_time=start_time,
            editorial_set=editorial_set,
        )

    def _assemble_result(
        self,
        *,
        query: str,
        query_dense_vector: list[float],
        language: str,
        teacher_id: Optional[str],
        cache_bypass: bool,
        request_allow_state: str,
        request_block_state: str,
        verified_clips: list[dict[str, Any]],
        clip_scores: list[float],
        top_clip: dict[str, Any],
        second_clip: Optional[dict[str, Any]],
        second_score: float,
        confidence: float,
        is_direct: bool,
        answerability: Optional[str],
        has_practice_intent: bool,
        n_quarantined: int,
        fp_llm_tokens: list[int],
        _ans_box: dict[str, Any],
        t_retrieval_ms: float,
        t_integrity_ms: float,
        t_rerank_ms: float,
        t_scorer_ms: float,
        start_time: float,
        editorial_set: Optional[dict[str, Any]] = None,
    ) -> FirstPersonPipelineResult:
        """Assemble the served answer: citations, clip metadata, cache write, metrics.

        The served text is the stored verbatim_text, byte for byte, and every rendered
        quote is re-checked against the payload it came from, so a quote whose
        speaker, link or timestamp is not backed by the store is never shown.
        Writes the exact cache (unless bypassed) and measures latency last, so
        scoring, citation building and the cache write are all counted.
        """
        from services.first_person_pipeline import (
            _CANONICAL_CONCEPTS,
            CITATION_PLAYBACK_PAD_S,
            UNTITLED_LINK_LABEL,
            FirstPersonPipelineResult,
            _speaker_verification,
            audio_strip_for,
            is_youtube_video_available,
            logger,
            match_okf_entries,
            settings,
            sources_from_payloads,
            time,
            transcript_label,
            verify_hero_clip,
        )

        # ponytail: retrieve matching OKF entries using in-memory vector matching (<1ms)
        okf_entries: list[dict[str, Any]] = []
        if query_dense_vector and len(query_dense_vector) == 1024:
            try:
                okf_entries = match_okf_entries(
                    query_dense_vector=query_dense_vector,
                    top_k=2,
                    teacher=teacher_id,
                    preferred_type="practice" if has_practice_intent else None,
                )
            except Exception as e:
                logger.warning(
                    "[FirstPersonPipeline] OKF matching failed: %s; proceeding with clips only", e
                )

        citations: list[dict[str, Any]] = []

        def _build_citation(
            clip: dict[str, Any], clip_confidence: float, provenance_kind: str
        ) -> dict[str, Any]:
            if provenance_kind == "curated_okf":
                raise ValueError("OKF entries cannot become first-person citations")
            sec = clip["start_ms"] // 1000
            video_id = clip["video_id"]
            playback_start = max(0.0, clip["start_ms"] / 1000.0 - CITATION_PLAYBACK_PAD_S)
            playback_end = clip["end_ms"] / 1000.0 + CITATION_PLAYBACK_PAD_S
            if clip.get("duration_ms"):
                playback_end = min(playback_end, clip["duration_ms"] / 1000.0)
            start_sec = int(clip["start_ms"]) // 1000
            end_sec = -(-int(clip["end_ms"]) // 1000) if clip.get("end_ms") else start_sec + 60
            clip_title = clip.get("title") or clip.get("video_title") or UNTITLED_LINK_LABEL
            clip_url = f"https://www.youtube.com/watch?v={video_id}&t={start_sec}s"
            return {
                "point_id": clip.get("point_id"),
                "video_id": video_id,
                "start_ms": clip["start_ms"],
                "end_ms": clip["end_ms"],
                "start_sec": start_sec,
                "end_sec": end_sec,
                "timestamp_seconds": sec,
                # Display attribution is copied from the stored, verified clip;
                # a guru ID is not evidence that the speaker label is correct.
                "speaker": clip.get("speaker"),
                "title": clip_title,
                "url": clip_url,
                "teacher_id": clip.get("teacher_id"),
                # Provenance claim copied from the stored clip, never inferred: the builder
                # writes True only after a real voice check and omits the key otherwise, so
                # a missing key must reach the UI as False, not as "verified" (QA-1).
                # A bare True with no recorded method is a claim without evidence and
                # reads as unverified (same rule as the corpus quality scorecard).
                "speaker_verified": _speaker_verification(clip)[0],
                "voice_verification_method": _speaker_verification(clip)[1],
                "channel": clip.get("channel"),
                "transcript_hash": clip["transcript_hash"],
                "verbatim_text": clip["verbatim_text"],
                "text_snippet": clip["verbatim_text"],
                # Always derived from the clip's own start: the stored source_url is the
                # plain video URL, which would open playback at 0:00.
                "source_url": clip_url,
                "video_url": clip.get("video_url") or f"https://www.youtube.com/watch?v={video_id}",
                "playback_start_seconds": round(playback_start, 2),
                "playback_end_seconds": round(playback_end, 2),
                "playback_url": f"https://www.youtube.com/watch?v={video_id}&t={int(playback_start)}s",
                "confidence": clip_confidence,
                "first_person_eligible": clip.get("first_person_eligible") is True,
                "rights_cleared": clip.get("rights_cleared") is True,
                "domain_rights_status": clip.get("domain_rights_status"),
                "is_verbatim": clip.get("is_verbatim") is True,
                "provenance_kind": provenance_kind,
                "caption_status": clip.get("caption_status") or "auto_transcript",
                **transcript_label(clip["verbatim_text"], clip.get("caption_status")),
            }

        # Every rendered quote (hero or weak match) is re-checked against the
        # payloads it was retrieved from: speaker label, link and t= must all be
        # backed by the stored record, or the quote is not shown (quote_fidelity).
        sources = sources_from_payloads(verified_clips)

        def _abstain_unverified() -> FirstPersonPipelineResult:
            latency = (time.monotonic() - start_time) * 1000.0
            stage_timings = {
                "answerability_ms": round(float(_ans_box.get("duration_ms", 0.0)), 2),
                "retrieval_ms": round(t_retrieval_ms, 2),
                "integrity_ms": round(t_integrity_ms, 2),
                "rerank_ms": round(t_rerank_ms, 2),
                "scorer_ms": round(t_scorer_ms, 2),
                "assembly_ms": 0.0,
                "total_ms": round(latency, 2),
            }
            self._log_and_count(
                "abstained",
                latency,
                confidence,
                n_quarantined,
                0,
                "no_verified_clips",
                sum(fp_llm_tokens),
            )
            return FirstPersonPipelineResult(
                answer_text="No verified first-person discourse found for this question.",
                citations=[],
                status="abstained",
                is_direct_answer=False,
                latency_ms=latency,
                answerability=answerability,
                abstain_reason="no_verified_clips",
                stage_timings=stage_timings,
            )

        t_asm_start = time.monotonic()
        if is_direct:
            status = "success"
            # Each served clip must clear the threshold itself; the top clip's
            # confidence says nothing about clips 2 and 3. Citations cover only
            # clips that will actually be rendered.
            threshold = self._profile["threshold"]
            confident = [
                (c, score)
                for c, score in zip(verified_clips, clip_scores)
                if score >= threshold
                and verify_hero_clip(c, sources) is not None
                and is_youtube_video_available(str(c.get("video_id") or ""))
            ]
            if not confident:
                return _abstain_unverified()
            confident_clips = [c for c, _ in confident]
            for clip, score in confident:
                cit = _build_citation(clip, score, clip.get("provenance_kind", "speech_turn_clip"))
                citations.append(cit)

            # ponytail: OKF entries are topic-matching signals only — never added to citations.
            # Citations must be 100% verbatim Qdrant clips. OKF summaries are LLM-generated
            # and must never appear as attributed guru words in the response or citation list.

            # ponytail: weave clips and OKF entries into structured answer
            intent = "PRACTICE" if has_practice_intent else "QUERY"
            weave_res = self._weaver.weave(
                query=query,
                clips=confident_clips,
                okf_entries=okf_entries,
                intent=intent,
                sources=sources,
                token_sink=fp_llm_tokens,
            )
            if not weave_res.passed_gate:
                return _abstain_unverified()
            final_text = weave_res.text
            audio_playback_clips = getattr(weave_res, "audio_playback_clips", None) or []
            if not audio_playback_clips and confident_clips:
                for c in confident_clips:
                    if not is_youtube_video_available(str(c.get("video_id") or "")):
                        continue
                    hero = verify_hero_clip(c, sources)
                    if hero:
                        strip = audio_strip_for(c, hero)
                        if strip:
                            audio_playback_clips.append(strip)
            audio_playback_clip = weave_res.audio_playback_clip or (
                audio_playback_clips[0] if audio_playback_clips else None
            )
            atma_vichara_inquiry = getattr(weave_res, "atma_vichara_inquiry", None)
            related_clips_heading = getattr(weave_res, "related_clips_heading", None)
            second_quote_note = None
            practice_recommendation = getattr(weave_res, "practice_recommendation", None)
            cit = citations[0] if citations else None
        else:
            status = "weak_match"
            hero = verify_hero_clip(top_clip, sources)
            if hero is None or not is_youtube_video_available(str(top_clip.get("video_id") or "")):
                return _abstain_unverified()
            cit = _build_citation(top_clip, confidence, "weak_match_fallback")
            citations.append(cit)
            if getattr(settings, "first_person_continuous_layout_enabled", False):
                from services.quote_weaver import (
                    _format_continuous_quote_block,
                    _format_continuous_sources_footer,
                )

                top_clip_with_hero = {**top_clip, "_hero": hero}
                quote_block = _format_continuous_quote_block(top_clip_with_hero)
                footer = _format_continuous_sources_footer([top_clip_with_hero])
                # The "Related, not a direct answer" label is signalled via
                # status="weak_match" + is_direct_answer=False + verification["direct"]=False.
                # Do NOT inject it into the answer text: the answer is the verbatim
                # clip; the UI layer owns the label rendering.
                final_text = quote_block + (f"\n{footer}" if footer else "")
            else:
                final_text = (
                    f'"{top_clip["verbatim_text"]}"\n'
                    f"— {hero['label']} ({top_clip['video_id']}, {cit['timestamp_seconds']}s)"
                )
            atma_vichara_inquiry = None
            related_clips_heading = None
            second_quote_note = None
            practice_recommendation = None
            audio_playback_clip = audio_strip_for(top_clip, hero)
            audio_playback_clips = [audio_playback_clip] if audio_playback_clip else []
            # Optional second quote: a separate recording that also answers, quoted exactly and
            # labelled as a different video that does not continue the first. Never merged text.
            # .get() reads throughout: a damaged point missing verbatim_text /
            # video_id / timing keys must drop the second quote (single-quote
            # path stands), never raise KeyError into a 500.
            second_hero = (
                verify_hero_clip(second_clip, sources) if second_clip is not None else None
            )
            second_text = (
                second_clip.get("verbatim_text") if isinstance(second_clip, dict) else None
            )
            second_vid = second_clip.get("video_id") if isinstance(second_clip, dict) else None
            top_text = top_clip.get("verbatim_text") if isinstance(top_clip, dict) else None
            top_vid = top_clip.get("video_id") if isinstance(top_clip, dict) else None
            if (
                second_clip is not None
                and second_hero is not None
                and second_text
                and second_vid
                and top_text
                and top_vid
                and is_youtube_video_available(str(second_vid))
            ):
                try:
                    cit2 = _build_citation(second_clip, second_score, "weak_match_fallback")
                except (KeyError, TypeError) as exc:
                    logger.warning(
                        "[FirstPersonPipeline] Second quote dropped (damaged point %s): %s",
                        second_clip.get("point_id"),
                        exc,
                    )
                    cit2 = None
                if cit2 is not None:
                    citations.append(cit2)
                    if getattr(settings, "first_person_continuous_layout_enabled", False):
                        from services.quote_weaver import (
                            _format_continuous_quote_block,
                            _format_continuous_sources_footer,
                        )

                        c1_with_hero = {**top_clip, "_hero": hero}
                        c2_with_hero = {**second_clip, "_hero": second_hero}
                        # Invariant 1: no facet headings inside the body. "first
                        # recording" / "second recording" are structure, and
                        # structure rides `second_quote_note` in metadata.
                        qb1 = _format_continuous_quote_block(c1_with_hero)
                        qb2 = _format_continuous_quote_block(c2_with_hero)
                        footer = _format_continuous_sources_footer([c1_with_hero, c2_with_hero])
                        final_text = f"{qb1}\n\n{qb2}" + (f"\n{footer}" if footer else "")
                    else:
                        # Same rule for the plain layout: two quote+attribution
                        # blocks, nothing else. The "these are separate recordings"
                        # framing is metadata, never body text.
                        final_text = (
                            f'"{top_text}"\n'
                            f"— {hero['label']} ({top_vid}, {cit['timestamp_seconds']}s)\n\n"
                            f'"{second_text}"\n'
                            f"— {second_hero['label']} ({second_vid}, {cit2['timestamp_seconds']}s)"
                        )
                    second_quote_note = (
                        "Two separate recordings, each quoted exactly. "
                        "Recording 2 is a different video; it does not continue the first."
                    )
                    strip2 = audio_strip_for(second_clip, second_hero)
                    if strip2:
                        audio_playback_clips.append(strip2)

        detected_concepts: list[str] = []
        seen_concepts = set()
        if okf_entries:
            for e in okf_entries:
                t = e.get("title")
                if t and t.lower() not in seen_concepts:
                    seen_concepts.add(t.lower())
                    detected_concepts.append(t)
        # _CANONICAL_CONCEPTS is module-level (A25) so the abstain related-clip
        # topic list reuses the exact same vocabulary.
        q_lower = query.lower()
        clip_text = (top_clip.get("verbatim_text") or "").lower() if top_clip else ""
        for c in _CANONICAL_CONCEPTS:
            if c.lower() in q_lower or c.lower() in clip_text:
                if c.lower() not in seen_concepts:
                    seen_concepts.add(c.lower())
                    detected_concepts.append(c)
            if len(detected_concepts) >= 4:
                break

        t_assembly_ms = (time.monotonic() - t_asm_start) * 1000.0

        stage_timings = {
            "answerability_ms": round(float(_ans_box.get("duration_ms", 0.0)), 2),
            "retrieval_ms": round(t_retrieval_ms, 2),
            "integrity_ms": round(t_integrity_ms, 2),
            "rerank_ms": round(t_rerank_ms, 2),
            "scorer_ms": round(t_scorer_ms, 2),
            "assembly_ms": round(t_assembly_ms, 2),
            "total_ms": round((time.monotonic() - start_time) * 1000.0, 2),
        }

        res = FirstPersonPipelineResult(
            answer_text=final_text,
            citations=citations,
            status=status,
            is_direct_answer=is_direct,
            latency_ms=0.0,
            answerability=answerability,  # 'yes' when the Phase 2 gate passed; None when it did not run
            abstain_reason="none",
            audio_playback_clip=audio_playback_clip,
            audio_playback_clips=audio_playback_clips,
            detected_concepts=detected_concepts,
            atma_vichara_inquiry=atma_vichara_inquiry,
            related_clips_heading=related_clips_heading,
            second_quote_note=second_quote_note,
            practice_recommendation=practice_recommendation,
            stage_timings=stage_timings,
            fp_served=bool(citations),
            editorial_set=editorial_set,
        )
        self._store_exact_cache(
            query=query,
            result=res,
            teacher_id=teacher_id,
            language=language,
            cache_bypass=cache_bypass,
            request_allow_state=request_allow_state,
            request_block_state=request_block_state,
        )

        # Measured last so scoring, citation building and the cache write are all counted.
        res.latency_ms = (time.monotonic() - start_time) * 1000.0
        res.stage_timings["total_ms"] = round(res.latency_ms, 2)
        logger.info(
            "[FirstPersonPipeline] Stage timings: ans=%.1fms, ret=%.1fms, int=%.1fms, rerank=%.1fms, scorer=%.1fms, asm=%.1fms, total=%.1fms",
            res.stage_timings["answerability_ms"],
            res.stage_timings["retrieval_ms"],
            res.stage_timings["integrity_ms"],
            res.stage_timings["rerank_ms"],
            res.stage_timings["scorer_ms"],
            res.stage_timings["assembly_ms"],
            res.stage_timings["total_ms"],
        )
        self._log_and_count(
            status,
            res.latency_ms,
            confidence,
            n_quarantined,
            len(citations),
            "none",
            sum(fp_llm_tokens),
        )
        return res

    def _execute_compound(
        self,
        query: str,
        facets: list[str],
        query_dense_vector: Optional[list[float]],
        query_sparse_vector: Optional[dict[str, list[float]]],
        teacher_id: Optional[str],
        max_clips: int,
        start_time: float,
        cache_bypass: bool,
        request_allow_state: str,
        request_block_state: str,
        fp_llm_tokens: list[int],
        language: str = "en",
        retrieval_query: str = "",
    ) -> FirstPersonPipelineResult:
        """Execute per-part retrieval, gating and continuous layout assembly for compound questions (Tasks F1 & F2)."""
        from services.first_person_pipeline import (
            _RELEVANCE_INDETERMINATE,
            FIRST_PERSON_QUARANTINED_TOTAL,
            FirstPersonPipelineResult,
            _answerability_check,
            _build_citation_dict,
            _passes_content_quality_gate,
            _passes_integrity_gate,
            _quality_allowlist,
            _quality_blocklist,
            _related_clips_for,
            _relevance_select,
            _speaker_verification,
            deduplicate_clips_by_video,
            first_person_evidence_policy,
            logger,
            settings,
            sources_from_payloads,
            time,
        )

        stage_timings: dict[str, float] = {
            "answerability_ms": 0.0,
            "retrieval_ms": 0.0,
            "integrity_ms": 0.0,
            "rerank_ms": 0.0,
            "scorer_ms": 0.0,
            "assembly_ms": 0.0,
            "total_ms": 0.0,
        }
        t_ret_start = time.monotonic()
        try:
            raw_clips = self._store.search_hybrid(
                query_dense_vector=query_dense_vector,
                query_sparse_vector=query_sparse_vector,
                teacher_id=teacher_id,
                limit=max(80, max_clips * 16),
                dedup_limit=max(40, max_clips * 8),
                deduplicate=False,
            )
        except Exception as e:
            logger.error(f"[FirstPersonPipeline] Compound retrieval failed: {e}")
            stage_timings["retrieval_ms"] = round((time.monotonic() - t_ret_start) * 1000.0, 2)
            stage_timings["total_ms"] = round((time.monotonic() - start_time) * 1000.0, 2)
            return FirstPersonPipelineResult(
                answer_text="An error occurred while retrieving first-person teachings.",
                citations=[],
                status="error",
                is_direct_answer=False,
                latency_ms=stage_timings["total_ms"],
                error=str(e),
                abstain_reason="none",
                stage_timings=stage_timings,
            )
        stage_timings["retrieval_ms"] = round((time.monotonic() - t_ret_start) * 1000.0, 2)

        # Integrity Gate
        t_int_start = time.monotonic()
        verified_clips: list[dict[str, Any]] = []
        n_quarantined = 0
        for clip in raw_clips:
            if _passes_integrity_gate(clip, boundary_guard_enabled=self._boundary_guard_enabled):
                if _passes_content_quality_gate(
                    clip, gate_enabled=self._content_quality_gate_enabled
                ):
                    if getattr(settings, "first_person_require_speaker_verified", False):
                        spk_ok, _ = _speaker_verification(clip)
                        if not (spk_ok or clip.get("speaker_verified") is True):
                            n_quarantined += 1
                            FIRST_PERSON_QUARANTINED_TOTAL.inc()
                            continue
                    verified_clips.append(clip)
                else:
                    n_quarantined += 1
            else:
                n_quarantined += 1

        if teacher_id and teacher_id.strip().lower() not in ("both", "all", ""):
            _want = teacher_id.strip().lower()
            verified_clips = [
                c for c in verified_clips if str(c.get("teacher_id") or "").lower() == _want
            ]
        _allow = _quality_allowlist()
        if _allow is not None:
            verified_clips = [c for c in verified_clips if str(c.get("point_id")) in _allow]
        _blocked = _quality_blocklist()
        if _blocked is not None:
            verified_clips = [c for c in verified_clips if str(c.get("point_id")) not in _blocked]
        elif str(getattr(settings, "first_person_quality_blocklist_path", "") or "").strip():
            # Configured-but-unreadable blocklist serves nothing (same fail-closed
            # contract as the single-question path).
            verified_clips = []
        verified_clips = [
            c
            for c in verified_clips
            if first_person_evidence_policy.assess_contextual_safety(
                query,
                str(c.get("verbatim_text") or ""),
                retrieval_query=retrieval_query,
            ).may_serve
        ]
        # T4-01 (RET-01): Gate first, then dedup per video.
        verified_clips = deduplicate_clips_by_video(
            verified_clips,
            max_clips=max(40, max_clips * 8),
        )
        stage_timings["integrity_ms"] = round((time.monotonic() - t_int_start) * 1000.0, 2)

        if not verified_clips:
            latency = (time.monotonic() - start_time) * 1000.0
            stage_timings["total_ms"] = round(latency, 2)
            return FirstPersonPipelineResult(
                answer_text="No verified first-person discourse found for this question.",
                citations=[],
                status="abstained",
                is_direct_answer=False,
                latency_ms=latency,
                abstain_reason="no_verified_clips",
                stage_timings=stage_timings,
            )

        # Answerability gate (invariant 22: it covers EVERY served clip). The compound
        # path used to skip it, so an out-of-scope compound question could be served
        # whatever clips the per-facet relevance scorer happened to accept.
        compound_answerability: Optional[str] = None
        if getattr(settings, "first_person_answerability_check_enabled", False):
            t_ans_start = time.monotonic()
            verdict = _answerability_check(
                retrieval_query or query,
                self._llm_service,
                request_loop=self._llm_loop,
                token_sink=fp_llm_tokens,
            )
            stage_timings["answerability_ms"] = round((time.monotonic() - t_ans_start) * 1000.0, 2)
            compound_answerability = (
                "yes" if verdict is True else ("no" if verdict is False else "indeterminate")
            )
            if verdict is not True:
                latency = (time.monotonic() - start_time) * 1000.0
                stage_timings["total_ms"] = round(latency, 2)
                self._log_and_count(
                    "abstained",
                    latency,
                    0.0,
                    n_quarantined,
                    0,
                    "answerability_withheld",
                    sum(fp_llm_tokens),
                )
                return FirstPersonPipelineResult(
                    answer_text="No verified first-person discourse found for this question.",
                    citations=[],
                    status="abstained",
                    is_direct_answer=False,
                    latency_ms=latency,
                    answerability="no" if verdict is False else "indeterminate",
                    abstain_reason="answerability_withheld",
                    stage_timings=stage_timings,
                )

        # Per-part Scoring & Selection (Task F2)
        t_scorer_start = time.monotonic()
        minimum_score = int(getattr(settings, "first_person_relevance_min_score", 3))
        used_video_ids: set[str] = set()
        part_results: list[dict[str, Any]] = []

        from services.quote_weaver import (
            audio_strip_for,
            verify_hero_clip,
        )

        sources = sources_from_payloads(verified_clips)

        for facet in facets:
            avail_clips = [c for c in verified_clips if c.get("video_id") not in used_video_ids]
            candidates = avail_clips[:3]
            rel_scores: list[int] = []
            if getattr(settings, "first_person_relevance_gate_enabled", True):
                pick = _relevance_select(
                    facet,
                    candidates,
                    self._llm_service,
                    self._llm_loop,
                    token_sink=fp_llm_tokens,
                    scores_out=rel_scores,
                )
            else:
                # Match the normal path's deterministic retrieval-order behavior
                # when the relevance gate is disabled; do not spend scorer/JEV calls.
                pick = 0 if candidates else None
            selected_score = (
                rel_scores[pick]
                if pick is not None and pick != _RELEVANCE_INDETERMINATE and pick < len(rel_scores)
                else None
            )
            # A facet earns a citation only from its own selected candidate and
            # only when that candidate clears the configured minimum.  In
            # particular, a below-min/zero facet is an honest gap; it may not
            # reuse a clip selected for an earlier facet.
            selected_is_eligible = (
                pick is not None
                and pick != _RELEVANCE_INDETERMINATE
                and (
                    not getattr(settings, "first_person_relevance_gate_enabled", True)
                    or (selected_score is not None and selected_score >= minimum_score)
                )
            )
            if selected_is_eligible:
                selected_clip = candidates[pick]
                used_video_ids.add(selected_clip.get("video_id"))
                part_results.append(
                    {
                        "facet": facet,
                        "clip": selected_clip,
                        "score": selected_score if selected_score is not None else minimum_score,
                    }
                )
            else:
                part_results.append(
                    {
                        "facet": facet,
                        "clip": None,
                        "score": 0,
                    }
                )
        stage_timings["scorer_ms"] = round((time.monotonic() - t_scorer_start) * 1000.0, 2)

        successful_parts = [p for p in part_results if p["clip"] is not None]
        if not successful_parts:
            latency = (time.monotonic() - start_time) * 1000.0
            stage_timings["total_ms"] = round(latency, 2)
            self._log_and_count(
                "abstained",
                latency,
                0.0,
                n_quarantined,
                0,
                "relevance_below_min",
                sum(fp_llm_tokens),
            )
            return FirstPersonPipelineResult(
                answer_text="No verified first-person discourse found for this question.",
                citations=[],
                status="abstained",
                is_direct_answer=False,
                latency_ms=latency,
                abstain_reason="relevance_below_min",
                stage_timings=stage_timings,
                # A25: below-min but integrity-verified — offer as related.
                related_clips=_related_clips_for(verified_clips),
            )

        # Assembly (Task F4 / Section 4 continuous layout)
        t_asm_start = time.monotonic()
        citations: list[dict[str, Any]] = []
        audio_playback_clips: list[dict[str, Any]] = []
        served_clips: list[dict[str, Any]] = []

        for p in part_results:
            clip = p["clip"]
            if clip is not None:
                hero = verify_hero_clip(clip, sources)
                if not hero:
                    continue
                clip_with_hero = {**clip, "_hero": hero}
                served_clips.append(clip_with_hero)

                cit = _build_citation_dict(
                    clip, clip_confidence=0.85, provenance_kind="compound_facet_clip"
                )
                citations.append(cit)
                strip = audio_strip_for(clip, hero)
                if strip:
                    audio_playback_clips.append(strip)

        if not served_clips:
            # Every selected clip failed hero verification: nothing quotable was
            # rendered, so serving the "Related, not a direct answer" shell with
            # zero citations (and caching it) would be an empty weak match.
            latency = (time.monotonic() - start_time) * 1000.0
            stage_timings["total_ms"] = round(latency, 2)
            self._log_and_count(
                "abstained",
                latency,
                0.0,
                n_quarantined,
                0,
                "no_verified_clips",
                sum(fp_llm_tokens),
            )
            return FirstPersonPipelineResult(
                answer_text="No verified first-person discourse found for this question.",
                citations=[],
                status="abstained",
                is_direct_answer=False,
                latency_ms=latency,
                abstain_reason="no_verified_clips",
                stage_timings=stage_timings,
            )

        # The evidence body contains source-verbatim text only. Facet headings,
        # missing-clip filler, and source lists are product/UI metadata, never
        # attributed to a teacher. Each source clip remains a separate block.
        final_text = "\n\n".join(
            str(clip.get("verbatim_text") or "").strip() for clip in served_clips
        )

        stage_timings["assembly_ms"] = round((time.monotonic() - t_asm_start) * 1000.0, 2)
        stage_timings["total_ms"] = round((time.monotonic() - start_time) * 1000.0, 2)

        rel_gate_on = bool(getattr(settings, "first_person_relevance_gate_enabled", True))
        compound_direct_on = (
            getattr(settings, "first_person_compound_direct_serving_enabled", True) is True
        )
        is_all_covered = len(successful_parts) == len(facets)
        is_direct = is_all_covered and len(facets) > 1 and rel_gate_on and compound_direct_on

        editorial_set = {
            "status": "supported" if is_all_covered else "partial",
            "candidate_facets": list(facets),
            "covered_facets": [p["facet"] for p in successful_parts],
            "facet_coverage": {p["facet"]: "direct" for p in successful_parts},
            "reasons": ("compound_facets_covered",)
            if is_all_covered
            else ("compound_facets_partial",),
            "content_safety": "clean",
        }

        compound_status = "success" if is_direct else "weak_match"
        res = FirstPersonPipelineResult(
            answer_text=final_text,
            citations=citations,
            status=compound_status,
            is_direct_answer=is_direct,
            editorial_set=editorial_set,
            latency_ms=stage_timings["total_ms"],
            answerability=compound_answerability,
            abstain_reason="none",
            audio_playback_clip=audio_playback_clips[0] if audio_playback_clips else None,
            audio_playback_clips=audio_playback_clips,
            stage_timings=stage_timings,
            fp_served=bool(citations),
        )
        if not cache_bypass:
            self.set_exact_cache(
                query,
                res.to_dict(),
                teacher_id,
                language=language,
                allow_state=request_allow_state,
                block_state=request_block_state,
            )

        logger.info(
            "[FirstPersonPipeline] Compound Timings: ans=%.1fms, ret=%.1fms, int=%.1fms, rerank=%.1fms, scorer=%.1fms, asm=%.1fms, total=%.1fms",
            res.stage_timings["answerability_ms"],
            res.stage_timings["retrieval_ms"],
            res.stage_timings["integrity_ms"],
            res.stage_timings["rerank_ms"],
            res.stage_timings["scorer_ms"],
            res.stage_timings["assembly_ms"],
            res.stage_timings["total_ms"],
        )
        self._log_and_count(
            compound_status,
            res.latency_ms,
            0.85,
            n_quarantined,
            len(citations),
            "none",
            sum(fp_llm_tokens),
        )
        return res
