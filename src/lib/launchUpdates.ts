import { supabase } from '@/integrations/supabase/client';

/**
 * Launch-update intake.
 *
 * The database owns validation: `public.subscribe_launch_updates` refuses
 * missing contact consent, malformed or oversized addresses, unknown sources,
 * and bursts above the intake cap. It returns the same `accepted` string for a
 * new address and an existing one, so this client must never try to learn
 * which case happened.
 */
export const LAUNCH_SIGNUP_SOURCES = [
  'guide_ai_spiritual_companion',
  'guide_serene_mind',
  'guide_spirit_guides',
  'guide_beautiful_state',
  'guide_self_centric',
  'guide_anxiety',
  'guide_suffering',
  'launch_page',
] as const;

export type LaunchSignupSource = (typeof LAUNCH_SIGNUP_SOURCES)[number];

export type LaunchSignupResult =
  | { status: 'accepted' }
  | { status: 'failed'; reason: 'invalid_email' | 'request_failed' };

/** Trim, lowercase and cap the address. The database re-normalizes it. */
export const sanitizeLaunchEmail = (raw: string): string =>
  raw.trim().toLowerCase().slice(0, 254);

/** Cheap client-side shape check. The database remains the authority. */
export const isPlausibleLaunchEmail = (raw: string): boolean => {
  const email = sanitizeLaunchEmail(raw);
  if (email.length < 5) return false;
  return /^[^\s@]+@[^\s@]+\.[A-Za-z]{2,}$/.test(email);
};

/**
 * Submit one consented launch subscription.
 *
 * Never logs or returns the address, and never reports whether it was already
 * present. `failed` is reported for both an invalid address and a transport or
 * database refusal; the caller shows one retry message.
 */
export async function submitLaunchSignup({
  email,
  source,
}: {
  email: string;
  source: LaunchSignupSource;
}): Promise<LaunchSignupResult> {
  const normalized = sanitizeLaunchEmail(email);
  if (!isPlausibleLaunchEmail(normalized)) {
    return { status: 'failed', reason: 'invalid_email' };
  }

  try {
    const { data, error } = await supabase.functions.invoke('launch-signup', {
      body: { email: normalized, consent: true, source },
    });
    if (error) return { status: 'failed', reason: 'request_failed' };
    return data?.status === 'accepted' ? { status: 'accepted' } : { status: 'failed', reason: 'request_failed' };
  } catch {
    return { status: 'failed', reason: 'request_failed' };
  }
}

/**
 * Withdraw consent and erase one address from the launch list.
 *
 * Requires the private per-subscriber token delivered in the confirmation email.
 * The database answers `accepted` without revealing membership. Never logs or returns the address.
 */
export async function submitLaunchErase(email: string, token: string | null): Promise<LaunchSignupResult> {
  const normalized = sanitizeLaunchEmail(email);
  if (!isPlausibleLaunchEmail(normalized)) {
    return { status: 'failed', reason: 'invalid_email' };
  }
  const t = (token ?? '').trim();
  if (!/^[0-9a-f-]{36}$/i.test(t)) return { status: 'failed', reason: 'request_failed' };
  const { data, error } = await supabase.rpc('erase_launch_subscription_with_token', { p_email: normalized, p_token: t });
  if (error) return { status: 'failed', reason: 'request_failed' };
  return data === 'accepted' ? { status: 'accepted' } : { status: 'failed', reason: 'request_failed' };
}
