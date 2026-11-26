export const SIGNUP_SOURCES = ['guide_ai_spiritual_companion', 'guide_serene_mind', 'guide_spirit_guides', 'guide_beautiful_state', 'guide_self_centric', 'guide_anxiety', 'guide_suffering', 'launch_page'];

export function validSignup(value: unknown): value is { email: string; source: string; consent: true } {
  if (!value || typeof value !== 'object') return false;
  const row = value as Record<string, unknown>;
  return row.consent === true && typeof row.email === 'string' && row.email.length <= 254
    && /^[^\s@]+@[^\s@]+\.[A-Za-z]{2,}$/.test(row.email.trim())
    && typeof row.source === 'string' && SIGNUP_SOURCES.includes(row.source);
}

export function unsubscribeLink(email: string, token: string): string {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(token)) throw new Error('Invalid private link');
  // Fragments are not sent to hosting servers, analytics request URLs or referrers.
  return `https://askmukthiguru.lovable.app/unsubscribe#${new URLSearchParams({ email, token })}`;
}

export function confirmationContent(link: string) {
  const text = `Welcome to AskMukthiGuru's launch list.\n\nYou requested occasional updates about new guides, practices and the launch. Start with spiritual reflection: https://askmukthiguru.lovable.app/guides/ai-spiritual-companion\n\nOr explore the 3-minute Serene Mind practice: https://askmukthiguru.lovable.app/guides/serene-mind-practice\n\nUnsubscribe and erase your email at any time: ${link}\n\nYour address is kept for up to 12 months. No account is required. AskMukthiGuru offers spiritual reflection, not medical or mental-health treatment.`;
  const safe = link.replaceAll('&', '&amp;').replaceAll('"', '&quot;');
  return {
    subject: 'Your AskMukthiGuru launch updates — and your private unsubscribe link',
    textContent: text,
    htmlContent: `<html><body style="background:#ffffff;color:#25251f;font-family:Georgia,serif;margin:0;padding:32px"><main style="max-width:560px;margin:auto"><p style="color:#856010">ASKMUKTHIGURU</p><h1 style="font-size:28px">A little space for reflection.</h1><p>You requested occasional updates about new guides, practices and the AskMukthiGuru launch.</p><p><a href="https://askmukthiguru.lovable.app/guides/ai-spiritual-companion">Read the spiritual guidance guide</a></p><p><a href="https://askmukthiguru.lovable.app/guides/serene-mind-practice">Explore the 3-minute Serene Mind practice</a></p><hr><p><a href="${safe}">Unsubscribe and erase my email</a></p><p style="font-size:13px">Kept for up to 12 months. No account required. Spiritual reflection, not medical or mental-health treatment.</p></main></body></html>`,
  };
}