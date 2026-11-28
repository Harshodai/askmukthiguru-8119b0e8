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
 * Reviewer claim, or an admin (same `has_role` RPC the admin guard uses; the
 * RLS policy accepts the same two predicates). Errors mean "not allowed".
 */
type ReviewUser = (NonNullable<Parameters<typeof hasFacultyReviewerRole>[0]> & { id?: string }) | null | undefined;

async function canReview(user: ReviewUser): Promise<boolean> {
  if (!user) return false;
  if (hasFacultyReviewerRole(user)) return true;
  if (!user.id) return false;
  const { data, error } = await supabase.rpc('has_role', { _user_id: user.id, _role: 'admin' });
  return !error && data === true;
}

/**
 * Mounts FacultyLabelPanel only for a faculty reviewer or an admin.
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
      .then(({ data }) => canReview(data?.user))
      .then((ok) => {
        if (!cancelled) setIsReviewer(ok);
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
