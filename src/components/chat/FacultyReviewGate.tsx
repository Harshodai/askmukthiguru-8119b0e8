import { useEffect, useState } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { isIncognitoMode } from '@/lib/chatStorage';
import { FacultyLabelPanel } from './FacultyLabelPanel';
import type { FacultyAnswerContext } from '@/lib/facultyLabels';

/** Build-time switch. Absent or anything but "true" means the panel never renders. */
const facultyReviewEnabled = (): boolean => import.meta.env.VITE_FACULTY_REVIEW_ENABLED === 'true';

interface FacultyReviewGateProps extends FacultyAnswerContext {
  /** True for crisis/helpline answers: the panel must never appear under them. */
  crisis: boolean;
}

/**
 * Mounts FacultyLabelPanel only when the build flag is on, the viewer is signed
 * in and not incognito, and the answer is not a crisis/helpline answer.
 */
export function FacultyReviewGate({ crisis, ...ctx }: FacultyReviewGateProps) {
  const enabled = facultyReviewEnabled() && !crisis;
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    void supabase.auth
      .getUser()
      .then(({ data }) => {
        if (!cancelled) setSignedIn(Boolean(data?.user?.id));
      })
      .catch(() => {
        if (!cancelled) setSignedIn(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  if (!enabled || !signedIn || isIncognitoMode()) return null;
  return <FacultyLabelPanel {...ctx} />;
}
