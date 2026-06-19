// Sarvam STT proxy — accepts multipart audio, returns transcript + detected language.
// POST multipart: file (audio blob), language_code
// -> { transcript: string, language_code: string }
import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text";

const toSarvamLang = (code: string): string => {
  if (!code) return "unknown";
  if (code === "unknown") return "unknown";
  if (code.includes("-")) return code;
  const map: Record<string, string> = {
    en: "en-IN", hi: "hi-IN", bn: "bn-IN", te: "te-IN", mr: "mr-IN",
    ta: "ta-IN", ur: "ur-IN", gu: "gu-IN", kn: "kn-IN", ml: "ml-IN",
    or: "od-IN", pa: "pa-IN",
  };
  return map[code] ?? `${code}-IN`;
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  try {
    const authHeader = req.headers.get("Authorization");
    if (!authHeader?.startsWith("Bearer ")) {
      return new Response(JSON.stringify({ error: "Unauthorized" }), {
        status: 401, headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }
    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_ANON_KEY")!,
    );
    const { data: userData, error: claimErr } = await supabase.auth.getUser(
      authHeader.replace("Bearer ", ""),
    );
    if (claimErr || !userData?.user) {
      return new Response(JSON.stringify({ error: "Unauthorized" }), {
        status: 401, headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const form = await req.formData();
    const file = form.get("file");
    const langRaw = String(form.get("language_code") ?? "unknown");
    if (!(file instanceof File) && !(file instanceof Blob)) {
      return new Response(JSON.stringify({ error: "file required" }), {
        status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }
    if ((file as Blob).size > 10 * 1024 * 1024) {
      return new Response(JSON.stringify({ error: "audio too large (>10MB)" }), {
        status: 413, headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const apiKey = Deno.env.get("SARVAM_API_KEY");
    if (!apiKey) {
      return new Response(JSON.stringify({ error: "STT not configured" }), {
        status: 503, headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const sarvamLang = toSarvamLang(langRaw);
    const upstream = new FormData();
    upstream.append("file", file as Blob, (file as File).name || "audio.webm");
    upstream.append("model", "saarika:v2.5");
    upstream.append("language_code", sarvamLang);
    upstream.append("with_diarization", "false");

    const sarvamRes = await fetch(SARVAM_STT_URL, {
      method: "POST",
      headers: { "api-subscription-key": apiKey },
      body: upstream,
    });

    if (!sarvamRes.ok) {
      const errText = await sarvamRes.text();
      console.error("Sarvam STT error", sarvamRes.status, errText);
      return new Response(
        JSON.stringify({ error: "An internal error occurred. Please try again." }),
        { status: 502, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    const data = await sarvamRes.json();
    return new Response(
      JSON.stringify({
        transcript: data?.transcript ?? "",
        language_code: data?.language_code ?? sarvamLang,
      }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  } catch (e) {
    console.error("sarvam-stt crash", e);
    return new Response(
      JSON.stringify({ error: "An internal error occurred. Please try again." }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }
});
