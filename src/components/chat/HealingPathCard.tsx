import { useEffect, useMemo, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, X, Check, Play, Clock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useHealingCourse } from '@/hooks/useHealingCourse';
import { BACKEND_URL } from '@/lib/backendUrl';
import { getAccessToken } from '@/lib/chat/auth';
import {
  courseForSignal,
  courseMinutes,
  detectSufferingSignal,
  getCourse,
  type HealingCourse,
  type SufferingSignal,
} from '@/lib/healingCourses';

/** Course assignment surfaced by the backend chat response. */
export interface HealingCourseRecommendation {
  slug: string;
  title: string;
  reason: string;
  trigger_signal: string;
}

export interface CourseTrigger {
  signal: SufferingSignal;
  pattern: 'consecutive_2' | 'freq_3_of_5' | 'escalation' | 'repeated_signal';
  reason: string;
}

export interface UserTurn {
  text: string;
  timestamp?: number;
}

interface HealingPathCardProps {
  /** Most recent seeker message. */
  lastUserText: string;
  /** Backend already flagged distress for this turn. */
  distressFlagged?: boolean;
  /** Streak-based course recommendation from the backend response. */
  recommendedCourse?: HealingCourseRecommendation | null;
  /** Recent seeker turns (text + ts) — used for local streak detection. */
  userTurnHistory?: UserTurn[];
  onAskGuru: (prompt: string) => void;
  onOpenSereneMind: () => void;
}

/**
 * Local streak detector — mirrors the backend trigger evaluator
 * (services/healing_course_service.py) over text-only turns. A single
 * distress message never triggers; only sustained patterns do.
 *
 * Pattern priority (text-only proxies): escalation (last 3 turns all
 * distressed with shifting signals — the closest text-only proxy for rising
 * severity), freq_3_of_5, consecutive_2, repeated_signal (same signal twice
 * within 24h).
 */
export function detectCourseTrigger(turns: UserTurn[] | undefined | null): CourseTrigger | null {
  if (!turns || turns.length === 0) return null;

  const lastThree = turns.slice(-3).map((t) => detectSufferingSignal(t.text));
  if (
    lastThree.length === 3 &&
    lastThree.every((s) => s !== null) &&
    new Set(lastThree).size >= 2
  ) {
    return {
      signal: lastThree[2] as SufferingSignal,
      pattern: 'escalation',
      reason: 'distress shifting across recent turns',
    };
  }

  const window = turns.slice(-5);
  const distressed = window.filter((t) => detectSufferingSignal(t.text) !== null);
  if (distressed.length >= 3) {
    const signal = detectSufferingSignal(distressed[distressed.length - 1].text) ?? 'general';
    return {
      signal,
      pattern: 'freq_3_of_5',
      reason: `distress in ${distressed.length} of last 5 turns`,
    };
  }

  let consecutive = 0;
  let lastSignal: SufferingSignal | null = null;
  for (const t of [...turns].reverse()) {
    const s = detectSufferingSignal(t.text);
    if (s) {
      consecutive += 1;
      lastSignal = s;
    } else {
      break;
    }
  }
  if (consecutive >= 2 && lastSignal) {
    return {
      signal: lastSignal,
      pattern: 'consecutive_2',
      reason: `${consecutive} consecutive distress turns`,
    };
  }

  const now = Date.now();
  const counts = new Map<SufferingSignal, number>();
  for (const t of turns) {
    const s = detectSufferingSignal(t.text);
    if (!s) continue;
    const ts = t.timestamp ?? now;
    if (now - ts > 24 * 3600 * 1000) continue;
    counts.set(s, (counts.get(s) ?? 0) + 1);
  }
  for (const [signal, count] of counts) {
    if (count >= 2) {
      return {
        signal,
        pattern: 'repeated_signal',
        reason: `'${signal}' distress signal repeated ${count}x within 24h`,
      };
    }
  }

  return null;
}

/**
 * When a seeker shows a sustained (streak-based) distress pattern, prescribe a
 * short sequenced path of teachings instead of a single answer. Sits above the
 * composer.
 */
export function HealingPathCard({
  lastUserText,
  recommendedCourse,
  userTurnHistory,
  onAskGuru,
  onOpenSereneMind,
}: HealingPathCardProps) {
  const { progress, enroll, completeLesson } = useHealingCourse();
  const [dismissed, setDismissed] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const assignAttemptedRef = useRef<string | null>(null);
  const prevCourseSlugRef = useRef<string | null>(null);

  const signal = useMemo(() => detectSufferingSignal(lastUserText), [lastUserText]);
  const trigger = useMemo(
    () => detectCourseTrigger(userTurnHistory ?? (lastUserText ? [{ text: lastUserText }] : [])),
    [userTurnHistory, lastUserText],
  );

  const activeSlug = Object.values(progress).find((p) => p.status === 'active')?.course_slug;
  const recommendedCourseObj = recommendedCourse ? getCourse(recommendedCourse.slug) ?? null : null;

  const course: HealingCourse | null = activeSlug
    ? getCourse(activeSlug) ?? null
    : recommendedCourseObj
      ? recommendedCourseObj
      : trigger
        ? courseForSignal(trigger.signal)
        : null;

  const state = course ? progress[course.slug] : undefined;
  const enrolled = Boolean(state);

  useEffect(() => {
    if (prevCourseSlugRef.current !== (course?.slug ?? null)) {
      setDismissed(false);
    }
    prevCourseSlugRef.current = course?.slug ?? null;
  }, [course?.slug]);

  useEffect(() => {
    if (!course || enrolled || assignAttemptedRef.current === course.slug) return;
    assignAttemptedRef.current = course.slug;
    const history = (userTurnHistory ?? []).map((t) => {
      const s = detectSufferingSignal(t.text);
      return {
        distress_level: s ? 2 : 0,
        signal: s ?? 'general',
        timestamp: (t.timestamp ?? Date.now()) / 1000,
      };
    });
    void (async () => {
      try {
        const token = await getAccessToken();
        await fetch(`${BACKEND_URL}/api/healing-course/assign`, {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ history }),
        });
      } catch {
        // Best-effort — the assignment is idempotent server-side.
      }
    })();
  }, [course, enrolled, userTurnHistory]);

  if (!course || dismissed) return null;

  const done = state?.completed_lessons ?? [];
  const total = course.lessons.length;
  const pct = Math.round((done.length / total) * 100);

  const triggerSignal = recommendedCourse?.trigger_signal ?? trigger?.signal ?? signal ?? 'general';
  const reason = recommendedCourse?.reason ?? trigger?.reason;

  const startLesson = (lessonId: string) => {
    const lesson = course.lessons.find((l) => l.id === lessonId);
    if (!lesson) return;
    if (!enrolled) enroll(course, triggerSignal, reason ?? 'Detected suffering in conversation');
    if (lesson.practice === 'serene-mind') onOpenSereneMind();
    else onAskGuru(lesson.guruPrompt);
    completeLesson(course.slug, lesson.id);
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 8 }}
        className="mx-auto mb-3 w-full max-w-3xl rounded-2xl border border-primary/20 bg-primary/[0.04] p-4 backdrop-blur-sm"
        role="region"
        aria-label="Healing path"
      >
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Sparkles className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] uppercase tracking-[0.18em] text-primary/80">
              {enrolled ? 'Your healing path' : 'A path for you'}
            </p>
            <h3 className="mt-0.5 font-serif text-base text-foreground">{course.title}</h3>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{course.subtitle}</p>
            {reason && (
              <p className="mt-1 text-xs text-primary/70">{reason}</p>
            )}

            <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {courseMinutes(course)} min · {total} steps
              </span>
              {enrolled && <span>{pct}% complete</span>}
            </div>

            {enrolled && (
              <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-border/50">
                <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${pct}%` }} />
              </div>
            )}

            <AnimatePresence initial={false}>
              {expanded && (
                <motion.ul
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="mt-3 space-y-2 overflow-hidden"
                >
                  {course.lessons.map((lesson, i) => {
                    const isDone = done.includes(lesson.id);
                    return (
                      <li
                        key={lesson.id}
                        className="flex items-start gap-3 rounded-xl border border-border/40 bg-background/60 p-3"
                      >
                        <span
                          className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] ${
                            isDone ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
                          }`}
                        >
                          {isDone ? <Check className="h-3 w-3" /> : i + 1}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm text-foreground">{lesson.title}</p>
                          <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{lesson.intention}</p>
                        </div>
                        <Button
                          size="sm"
                          variant={isDone ? 'ghost' : 'secondary'}
                          className="shrink-0"
                          onClick={() => startLesson(lesson.id)}
                        >
                          <Play className="mr-1 h-3 w-3" />
                          {lesson.minutes}m
                        </Button>
                      </li>
                    );
                  })}
                </motion.ul>
              )}
            </AnimatePresence>

            <div className="mt-3 flex flex-wrap gap-2">
              <Button
                size="sm"
                onClick={() => {
                  if (!enrolled) enroll(course, triggerSignal, reason ?? 'Detected suffering in conversation');
                  setExpanded((v) => !v);
                }}
              >
                {enrolled ? (expanded ? 'Hide steps' : 'Continue path') : 'Begin this path'}
              </Button>
              <Button size="sm" variant="ghost" onClick={onOpenSereneMind}>
                Serene Mind now
              </Button>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setDismissed(true)}
            className="rounded-full p-1 text-muted-foreground/70 transition hover:bg-muted hover:text-foreground"
            aria-label="Dismiss healing path"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
