/**
 * useVisitContext.ts
 * ─────────────────────────────────────────────────────────────────────────────
 * Hook that determines the greeting context for the current session:
 *   • "first_visit"      — user has NEVER seen the landing/chat page before
 *   • "return_same_day"  — user already has a visit record for today (same calendar day)
 *   • "return_new_day"   — user is back after a previous day (most common case)
 *
 * Persistence: a single `askmukthiguru_visit` key in localStorage.
 * The value is a JSON object { lastVisitDate: ISO date string, totalVisits: number }.
 *
 * This hook runs once per mount. The `context` value is stable for the lifetime
 * of the component, so it can safely be passed to `buildGreeting`.
 */

import { useEffect, useState } from 'react';
import type { GreetingContext } from '@/lib/greeting';

const STORAGE_KEY = 'askmukthiguru_visit';

interface VisitRecord {
  lastVisitDate: string;   // ISO date "2026-07-07"
  totalVisits: number;
}

const todayISO = (): string => new Date().toISOString().slice(0, 10);

function loadRecord(): VisitRecord | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as VisitRecord;
  } catch {
    return null;
  }
}

function saveRecord(record: VisitRecord): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(record));
  } catch {
    // localStorage may be unavailable (private browsing / storage full)
  }
}

function resolveContext(record: VisitRecord | null): GreetingContext {
  if (!record) return 'first_visit';
  const today = todayISO();
  if (record.lastVisitDate === today) return 'return_same_day';
  return 'return_new_day';
}

export interface UseVisitContextResult {
  /** Greeting context to pass to buildGreeting / buildGreetingSubline. */
  greetingContext: GreetingContext;
  /** Total number of previous visits (0 on first visit). */
  totalVisits: number;
  /** True if this is the user's very first session ever. */
  isFirstVisit: boolean;
}

export function useVisitContext(): UseVisitContextResult {
  const [result, setResult] = useState<UseVisitContextResult>(() => {
    // Compute synchronously so first render already has the right context.
    const record = loadRecord();
    const context = resolveContext(record);
    const total = record?.totalVisits ?? 0;
    return {
      greetingContext: context,
      totalVisits: total,
      isFirstVisit: context === 'first_visit',
    };
  });

  useEffect(() => {
    // Update the record after we've determined context (not before, so we don't
    // corrupt the context for the current render cycle).
    const today = todayISO();
    const record = loadRecord();
    const newRecord: VisitRecord = {
      lastVisitDate: today,
      totalVisits: (record?.totalVisits ?? 0) + 1,
    };
    saveRecord(newRecord);
  }, []); // run once per mount

  return result;
}
