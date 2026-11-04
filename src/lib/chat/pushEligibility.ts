/**
 * T1-10 (PRD-004): the push-permission prompt is an engagement nudge. It must
 * never follow a safety, distress or abstain turn. It fires only after a
 * grounded teaching answer (route_decision `first_person_bridge`, the
 * verbatim-clip route) with no safety notice and no proactive Serene Mind
 * (distress) signal.
 */
const TEACHING_ROUTES: ReadonlySet<string> = new Set(['first_person_bridge']);

export interface PushEligibilityInput {
  blocked?: boolean | null;
  groundingState?: string | null;
  routeDecision?: string | null;
  isFirstPersonAbstain?: boolean | null;
  safetyNotices?: readonly string[] | null;
  /** Any proactive Serene Mind / distress signal from the backend. */
  proactiveSereneMind?: unknown;
}

export function isPushPromptEligible(input: PushEligibilityInput): boolean {
  if (input.blocked) return false;
  if (input.groundingState !== 'grounded') return false;
  if (input.isFirstPersonAbstain) return false;
  if (!input.routeDecision || !TEACHING_ROUTES.has(input.routeDecision)) return false;
  if (input.safetyNotices && input.safetyNotices.length > 0) return false;
  if (input.proactiveSereneMind) return false;
  return true;
}
