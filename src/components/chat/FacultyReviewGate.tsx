import { useEffect, useState } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { isIncognitoMode } from '@/lib/chatStorage';
import { FacultyLabelPanel } from './FacultyLabelPanel';
import type { FacultyAnswerContext } from '@/lib/facultyLabels';

/** Build-time switch. Absent or anything but "true" means the panel never renders. */
const facultyReviewEnabled = (): boolean => import.meta.env.VITE_FACULTY_REVIEW_ENABLED === 'true';

/** Presentation guard only. Database RLS remains the authority for writes. */
export const hasFacultyReviewerRole = (user: {
  app_metadata?: Record<string, unknown> | null;
  user_metadata?: Record<string, unknown> | null;
} | null | undefined): boolean =>
  user?.app_metadata?.role === 'faculty_reviewer';

interface FacultyReviewGateProps extends FacultyAnswerContext {
  /** True for crisis/helpline answers: the panel must never appear under them. */
  crisis: boolean;
}

/**
 * Mounts FacultyLabelPanel only for an explicitly provisioned faculty reviewer.
 * A flag, ordinary sign-in, or user-editable metadata is never sufficient.
 */
export function FacultyReviewGate({ crisis, ...ctx }: FacultyReviewGateProps) {
  const enabled = facultyReviewEnabled() && !crisis;
  const [isReviewer, setIsReviewer] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    void supabase.auth
      .getUser()
      .then(({ data }) => {
        if (!cancelled) setIsReviewer(hasFacultyReviewerRole(data?.user));
      })
      .catch(() => {
        if (!cancelled) setIsReviewer(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  if (!enabled || !isReviewer || isIncognitoMode()) return null;
  return <FacultyLabelPanel {...ctx} />;
}
