import { createClient } from 'npm:@supabase/supabase-js@2';
import { corsHeaders } from 'npm:@supabase/supabase-js@2/cors';
import { validSignup, unsubscribeLink, confirmationContent } from './email.ts';

const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { ...corsHeaders, 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } });

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });
  if (req.method !== 'POST') return reply({ error: 'Method not allowed' }, 405);
  if (Number(req.headers.get('content-length') ?? 0) > 2048) return reply({ error: 'Request too large' }, 413);
  try {
    const raw = await req.text();
    if (raw.length > 2048) return reply({ error: 'Request too large' }, 413);
    const body: unknown = JSON.parse(raw);
    const retry = Boolean(body && typeof body === 'object' && 'action' in body && body.action === 'retry');
    if (!retry && !validSignup(body)) return reply({ error: 'Valid email, source and contact consent required' }, 400);
    const email = validSignup(body) ? body.email.trim().toLowerCase() : null;
    const url = Deno.env.get('SUPABASE_URL');
    const anonKey = Deno.env.get('SUPABASE_ANON_KEY');
    const serviceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');
    const gatewayKey = Deno.env.get('LOVABLE_API_KEY');
    const brevoKey = Deno.env.get('BREVO_API_KEY');
    if (!url || !anonKey || !serviceKey || !gatewayKey || !brevoKey) return reply({ error: 'Signup service unavailable' }, 503);

    const db = createClient(url, serviceKey, { auth: { persistSession: false } });
    if (retry) {
      const token = (req.headers.get('Authorization') ?? '').replace(/^Bearer /, '');
      const { data: auth, error: authError } = await db.auth.getUser(token);
      if (authError || !auth.user) return reply({ error: 'Sign in required' }, 401);
      let aal = '';
      try { aal = JSON.parse(atob(token.split('.')[1].replaceAll('-', '+').replaceAll('_', '/'))).aal; } catch { /* denied below */ }
      const role = await db.from('user_roles').select('user_id').eq('user_id', auth.user.id).eq('role', 'admin').maybeSingle();
      if (role.error || !role.data || aal !== 'aal2') return reply({ error: 'Admin MFA required' }, 403);
    }
    // Public intake retains database validation/throttling; never use elevated privileges for signup.
    const intake = createClient(url, anonKey, { auth: { persistSession: false }, global: { headers: { 'x-forwarded-for': req.headers.get('x-forwarded-for') ?? '' } } });
    if (validSignup(body)) {
      const { data, error } = await intake.rpc('subscribe_launch_updates', { p_email: email, p_consent: true, p_source: body.source });
      if (error || data !== 'accepted') return reply({ error: 'Could not save signup. Please try again.' }, 503);
      const queued = await db.rpc('queue_existing_launch_confirmation', { p_email: email });
      if (queued.error) console.error('launch confirmation enqueue failed', queued.error.code);
    }
    const claimed = await db.rpc('claim_launch_confirmations', { p_email: email, p_limit: retry ? 5 : 1 });
    if (claimed.error) console.error('launch confirmation claim failed', claimed.error.code);
    for (const job of claimed.data ?? []) {
      try {
        const current = await db.from('waitlist_entries').select('id').eq('id', job.subscriber_id).eq('consent_to_contact', true).maybeSingle();
        if (current.error || !current.data) continue;
        const response = await fetch('https://connector-gateway.lovable.dev/brevo/smtp/email', {
          method: 'POST', redirect: 'error', signal: AbortSignal.timeout(12_000),
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${gatewayKey}`, 'X-Connection-Api-Key': brevoKey },
          body: JSON.stringify({
            sender: { name: 'AskMukthiGuru', email: Deno.env.get('LAUNCH_SENDER_EMAIL') ?? 'kharshaengineer@gmail.com' },
            to: [{ email: job.email }],
            ...confirmationContent(unsubscribeLink(job.email, job.unsubscribe_token)),
            tags: ['launch-confirmation'],
            headers: { 'X-Mailin-custom': `launch_id:${job.subscriber_id}` },
          }),
        });
        if (!response.ok) {
          const details = await response.text();
          // Provider bodies can include recipients; keep private details out of public responses/logs.
          console.error('Brevo confirmation refused', response.status, details.replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[email]'));
          throw new Error(`provider_${response.status}`);
        }
        const receipt = await response.json();
        if (typeof receipt.messageId !== 'string') throw new Error('provider_receipt_missing');
        const saved = await db.from('launch_email_deliveries').update({ state: 'accepted', provider_message_id: receipt.messageId, locked_at: null, last_error: null }).eq('subscriber_id', job.subscriber_id).eq('attempts', job.attempts);
        if (saved.error) console.error('launch provider receipt persistence failed', saved.error.code);
      } catch (err) {
        const reason = err instanceof Error && /^provider_\d+$/.test(err.message) ? err.message : 'send_unconfirmed';
        await db.from('launch_email_deliveries').update({ state: 'failed', last_error: reason, locked_at: null, next_attempt_at: new Date(Date.now() + 60_000).toISOString() }).eq('subscriber_id', job.subscriber_id).eq('attempts', job.attempts);
      }
    }
    // Same public result for a new/duplicate address and provider success/failure.
    return reply(retry ? { status: 'accepted', attempted: (claimed.data ?? []).length } : { status: 'accepted' });
  } catch {
    return reply({ error: 'Could not save signup. Please try again.' }, 400);
  }
});