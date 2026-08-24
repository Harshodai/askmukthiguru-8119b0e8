import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.0";

// This function used to send Web Push directly with its own copy of the
// webpush-sending logic — a second cron sender with no stale-subscription
// cleanup and a payload schema that diverged from push-send's. Two senders
// could double-send the same teaching and drift in behavior. Consolidated to
// delegate to push-send, which owns sending, stale (404/410) cleanup, and the
// deep-link allowlist. (OH-P1-05, 2026-08-24)
Deno.serve(async (req) => {
  const cronSecret = Deno.env.get("CRON_SECRET");
  const provided = req.headers.get("x-cron-secret");
  if (!cronSecret || provided !== cronSecret) {
    return new Response(JSON.stringify({ error: "unauthorized" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  const sb = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );
  const { data: teaching } = await sb.from("daily_teachings")
    .select("caption, image_url")
    .order("publish_date", { ascending: false })
    .limit(1)
    .single();

  const res = await fetch(`${Deno.env.get("SUPABASE_URL")}/functions/v1/push-send`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-cron-secret": cronSecret,
    },
    body: JSON.stringify({
      title: "Today's Teaching",
      body: teaching?.caption ?? "",
      url: "/chat",
      ...(teaching?.image_url ? { image: teaching.image_url } : {}),
    }),
  });
  const result = await res.json().catch(() => ({}));
  return new Response(JSON.stringify(result), {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
});
