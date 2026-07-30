import { useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, X, Check, Play, Clock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useHealingCourse } from '@/hooks/useHealingCourse';
import {
  courseForSignal,
  courseMinutes,
  detectSufferingSignal,
  getCourse,
  type HealingCourse,
} from '@/lib/healingCourses';

interface HealingPathCardProps {
  /** Most recent seeker message — used to detect the suffering signal. */
  lastUserText: string;
  /** Backend already flagged distress for this turn. */
  distressFlagged?: boolean;
  onAskGuru: (prompt: string) => void;
  onOpenSereneMind: () => void;
}

/**
 * When a seeker is in suffering, prescribe a short sequenced path of
 * teachings instead of a single answer. Sits above the composer.
 */
export function HealingPathCard({
  lastUserText,
  distressFlagged,
  onAskGuru,
  onOpenSereneMind,
}: HealingPathCardProps) {
  const { progress, enroll, completeLesson } = useHealingCourse();
  const [dismissed, setDismissed] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const signal = useMemo(() => detectSufferingSignal(lastUserText), [lastUserText]);

  const activeSlug = Object.values(progress).find((p) => p.status === 'active')?.course_slug;
  const course: HealingCourse | null = activeSlug
    ? getCourse(activeSlug) ?? null
    : signal || distressFlagged
      ? courseForSignal(signal ?? 'general')
      : null;

  if (!course || dismissed) return null;

  const state = progress[course.slug];
  const done = state?.completed_lessons ?? [];
  const total = course.lessons.length;
  const pct = Math.round((done.length / total) * 100);
  const enrolled = Boolean(state);

  const startLesson = (lessonId: string) => {
    const lesson = course.lessons.find((l) => l.id === lessonId);
    if (!lesson) return;
    if (!enrolled) enroll(course, signal ?? 'general', 'Detected suffering in conversation');
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
                  if (!enrolled) enroll(course, signal ?? 'general', 'Detected suffering in conversation');
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
