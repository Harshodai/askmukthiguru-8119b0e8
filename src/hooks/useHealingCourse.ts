import { useCallback, useEffect, useState } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { getCourse, type HealingCourse } from '@/lib/healingCourses';

export interface CourseProgress {
  course_slug: string;
  completed_lessons: string[];
  current_lesson_index: number;
  status: string;
  assigned_reason?: string | null;
  trigger_signal?: string | null;
}

const LS_KEY = 'askmukthiguru_healing_progress';

function readLocal(): Record<string, CourseProgress> {
  try {
    return JSON.parse(localStorage.getItem(LS_KEY) || '{}');
  } catch {
    return {};
  }
}

function writeLocal(all: Record<string, CourseProgress>) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(all));
  } catch {
    /* quota — progress is non-critical */
  }
}

/**
 * Healing path enrollment + progress.
 * DB-backed for authenticated seekers, localStorage for anonymous ones.
 */
export function useHealingCourse() {
  const [userId, setUserId] = useState<string | null>(null);
  const [progress, setProgress] = useState<Record<string, CourseProgress>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const { data } = await supabase.auth.getSession();
      const uid = data.session?.user?.id ?? null;
      if (cancelled) return;
      setUserId(uid);

      if (!uid) {
        setProgress(readLocal());
        setLoading(false);
        return;
      }

      const { data: rows, error } = await supabase
        .from('user_course_progress')
        .select('course_slug, completed_lessons, current_lesson_index, status, assigned_reason, trigger_signal')
        .eq('user_id', uid);

      if (cancelled) return;
      if (error) {
        setProgress(readLocal());
      } else {
        const map: Record<string, CourseProgress> = {};
        for (const r of rows ?? []) map[r.course_slug] = r as CourseProgress;
        setProgress(map);
      }
      setLoading(false);
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const persist = useCallback(
    async (next: CourseProgress) => {
      setProgress((prev) => ({ ...prev, [next.course_slug]: next }));

      if (!userId) {
        const all = readLocal();
        all[next.course_slug] = next;
        writeLocal(all);
        return;
      }

      await supabase.from('user_course_progress').upsert(
        {
          user_id: userId,
          course_slug: next.course_slug,
          completed_lessons: next.completed_lessons,
          current_lesson_index: next.current_lesson_index,
          status: next.status,
          assigned_reason: next.assigned_reason ?? null,
          trigger_signal: next.trigger_signal ?? null,
          completed_at: next.status === 'completed' ? new Date().toISOString() : null,
        },
        { onConflict: 'user_id,course_slug' },
      );
    },
    [userId],
  );

  const enroll = useCallback(
    (course: HealingCourse, signal?: string, reason?: string) => {
      const existing = progress[course.slug];
      if (existing) return existing;
      const next: CourseProgress = {
        course_slug: course.slug,
        completed_lessons: [],
        current_lesson_index: 0,
        status: 'active',
        trigger_signal: signal ?? null,
        assigned_reason: reason ?? null,
      };
      void persist(next);
      return next;
    },
    [progress, persist],
  );

  const completeLesson = useCallback(
    (slug: string, lessonId: string) => {
      const course = getCourse(slug);
      const current =
        progress[slug] ??
        ({ course_slug: slug, completed_lessons: [], current_lesson_index: 0, status: 'active' } as CourseProgress);
      if (current.completed_lessons.includes(lessonId)) return;

      const completed = [...current.completed_lessons, lessonId];
      const total = course?.lessons.length ?? completed.length;
      void persist({
        ...current,
        completed_lessons: completed,
        current_lesson_index: Math.min(completed.length, total - 1),
        status: completed.length >= total ? 'completed' : 'active',
      });
    },
    [progress, persist],
  );

  const activeCourse = Object.values(progress).find((p) => p.status === 'active') ?? null;

  return { progress, activeCourse, loading, enroll, completeLesson };
}
