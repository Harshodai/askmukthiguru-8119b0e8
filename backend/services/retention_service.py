from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class StreakState:
    current: int = 0
    longest: int = 0
    last_active: Optional[str] = None
    freezes_available: int = 1
    total_days: int = 0


class StreakEngine:
    FREEZE_REGEN_DAYS = 14

    def record_practice(self, state: StreakState, on: Optional[date] = None) -> StreakState:
        today = (on or date.today()).isoformat()
        if state.last_active == today:
            return state

        yesterday = (on or date.today()) - timedelta(days=1)
        if state.last_active == yesterday.isoformat():
            state.current += 1
        elif state.last_active is None:
            state.current = 1
        else:
            gap = (on or date.today()) - date.fromisoformat(state.last_active)
            if gap.days == 2 and state.freezes_available > 0:
                state.freezes_available -= 1
                state.current += 1
            else:
                state.current = 1

        state.last_active = today
        state.total_days += 1
        state.longest = max(state.longest, state.current)
        if state.total_days % self.FREEZE_REGEN_DAYS == 0:
            state.freezes_available = min(2, state.freezes_available + 1)
        return state

    def at_risk(self, state: StreakState, today: Optional[date] = None) -> bool:
        if not state.last_active:
            return False
        gap = (today or date.today()) - date.fromisoformat(state.last_active)
        return gap.days >= 2


EV_SIGNUP = "signup"
EV_FIRST_ANSWER = "first_answer"
EV_PRACTICE = "practice"
EV_STREAK = "streak_milestone"
EV_RETURN = "return"
EV_AT_RISK = "at_risk"
EV_WINBACK_SENT = "winback_sent"

STREAK_MILESTONES = (3, 7, 14, 21, 40, 108)


class RetentionService:
    def __init__(self, supabase_client: Any):
        self._supabase = supabase_client
        self._engine = StreakEngine()

    async def _load_state(self, user_id: str) -> StreakState:
        if not user_id or not user_id.strip():
            return StreakState()
        res = self._supabase.table("user_streaks").select("*").eq("user_id", user_id).maybe_single().execute()
        row = res.data if res.data else {}
        if not row:
            return StreakState()
        return StreakState(
            current=row.get("current_streak", 0),
            longest=row.get("longest_streak", 0),
            last_active=row.get("last_active_date"),
            freezes_available=row.get("freezes_available", 1),
            total_days=row.get("total_practice_days", 0),
        )

    async def _save_state(self, user_id: str, state: StreakState) -> None:
        self._supabase.table("user_streaks").upsert({
            "user_id": user_id,
            "current_streak": state.current,
            "longest_streak": state.longest,
            "last_active_date": state.last_active,
            "freezes_available": state.freezes_available,
            "total_practice_days": state.total_days,
        }).execute()

    async def _log_event(self, user_id: str, event: str, **props) -> None:
        self._supabase.table("retention_events").insert({
            "user_id": user_id,
            "event": event,
            "props": props,
        }).execute()

    async def get_streak(self, user_id: str) -> StreakState:
        return await self._load_state(user_id)

    async def record_practice(self, user_id: str, on: Optional[date] = None) -> StreakState:
        if not user_id or not user_id.strip():
            return StreakState()
        try:
            from datetime import timezone as tz
            rpc_on = (on or date.today()).isoformat()
            res = self._supabase.rpc(
                "record_practice",
                {"p_user_id": user_id, "p_practice_date": rpc_on},
            ).execute()
            row = res.data[0] if res.data else None
            if row:
                return StreakState(
                    current=row.get("current_streak", 0),
                    longest=row.get("longest_streak", 0),
                    last_active=row.get("last_active_date"),
                    freezes_available=row.get("freezes_available", 1),
                    total_days=row.get("total_practice_days", 0),
                )
        except Exception:
            logger.warning("atomic record_practice failed, falling back to client-side", exc_info=True)

        state = await self._load_state(user_id)
        before = state.current
        state = self._engine.record_practice(state, on=on)
        await self._save_state(user_id, state)
        await self._log_event(user_id, EV_PRACTICE, streak_current=state.current)

        if state.current in STREAK_MILESTONES and state.current != before:
            await self._log_event(user_id, EV_STREAK, streak=state.current)

        return state

    async def at_risk(self, user_id: str, today: Optional[date] = None) -> bool:
        state = await self._load_state(user_id)
        return self._engine.at_risk(state, today=today)

    async def retention_curve(self, horizon_days: int = 30, eval_ts: Optional[float] = None) -> dict[int, float]:
        """Calculate retention curve.
        
        Args:
            horizon_days: Maximum retention horizon (e.g., 30 for D30)
            eval_ts: Explicit evaluation timestamp (Unix epoch). Defaults to current time.
                     Allows historical cohort analysis at a specific point in time.
        """
        now_ts = eval_ts if eval_ts is not None else time.time()
        # Expand signup query window backward by the largest requested horizon
        # so cohorts have time to mature through D30 while we evaluate at eval_ts
        max_horizon = horizon_days
        cutoff = now_ts - max_horizon * 86400 - max_horizon * 86400  # 2x horizon for signup window
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
        # Activity window ends at eval_ts
        activity_cutoff_iso = datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()
        signups_res = self._supabase.table("retention_events").select("user_id, created_at").eq("event", EV_SIGNUP).gte("created_at", cutoff_iso).execute()
        activity_res = self._supabase.table("retention_events").select("user_id, created_at").eq("event", EV_PRACTICE).gte("created_at", cutoff_iso).lte("created_at", activity_cutoff_iso).execute()

        signups = []
        for r in (signups_res.data or []):
            ts = r.get("created_at")
            if ts:
                signups.append({"user_id": r["user_id"], "ts": datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()})

        activities = []
        for r in (activity_res.data or []):
            ts = r.get("created_at")
            if ts:
                activities.append({"user_id": r["user_id"], "ts": datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()})

        return _retention_curve(signups, activities, horizons=tuple(range(1, horizon_days + 1)) if horizon_days <= 30 else (1, 7, 30), eval_ts=now_ts)


def _retention_curve(signup_events: list[dict], activity_events: list[dict],
                     horizons=(1, 7, 30), eval_ts: Optional[float] = None) -> dict[int, float]:
    last_seen: dict[str, float] = {}
    for e in activity_events:
        u, ts = e["user_id"], e["ts"]
        last_seen[u] = max(last_seen.get(u, 0.0), ts)

    out: dict[int, float] = {}
    now = eval_ts if eval_ts is not None else (max(e["ts"] for e in activity_events) if activity_events else (max((e["ts"] for e in signup_events), default=0)))
    signups = {e["user_id"]: e["ts"] for e in signup_events}
    for h in horizons:
        retained = 0
        eligible = 0
        for u, s_ts in signups.items():
            if s_ts + h * 86400 <= now:
                eligible += 1
                act = last_seen.get(u)
                if act is not None and act >= s_ts + h * 86400 - 3600:
                    retained += 1
        out[h] = round(retained / eligible, 4) if eligible else 0.0
    return out


if __name__ == "__main__":
    eng = StreakEngine()
    s = StreakState()
    d = date(2026, 7, 1)
    s = eng.record_practice(s, d)
    s = eng.record_practice(s, d + timedelta(days=1))
    assert s.current == 2
    s = eng.record_practice(s, d + timedelta(days=3))
    assert s.current == 3 and s.freezes_available == 0, s
    s = eng.record_practice(s, d + timedelta(days=20))
    assert s.current == 1
    print("streak engine self-test OK")

    signups = [{"user_id": "a", "ts": 0}, {"user_id": "b", "ts": 0}]
    activity = [{"user_id": "a", "ts": 2 * 86400}, {"user_id": "a", "ts": 8 * 86400}]
    curve = _retention_curve(signups, activity)
    assert curve[1] == 0.5 and curve[7] == 0.5 and curve[30] == 0.0, curve
    print("retention curve self-test OK", curve)
