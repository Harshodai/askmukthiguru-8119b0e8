import webpush from "npm:web-push@3.6.7";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.0";

webpush.setVapidDetails(
  "mailto:hello@askmukthiguru.com",
  Deno.env.get("VAPID_PUBLIC_KEY")!,
  Deno.env.get("VAPID_PRIVATE_KEY")!,
);

Deno.serve(async () => {
  const sb = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );
  const { data: teaching } = await sb.from("daily_teachings")
    .select("caption, image_url")
    .order("publish_date", { ascending: false })
    .limit(1)
    .single();
  const { data: subs } = await sb.from("push_subscriptions").select("*");
  const payload = JSON.stringify({
    title: "Today's Teaching",
    body: teaching?.caption ?? "",
    image: teaching?.image_url,
  });
  await Promise.allSettled(
    (subs ?? []).map((s) =>
      webpush.sendNotification(
        { endpoint: s.endpoint, keys: { p256dh: s.p256dh, auth: s.auth } },
        payload,
      )
    ),
  );
  return new Response("ok");
});
