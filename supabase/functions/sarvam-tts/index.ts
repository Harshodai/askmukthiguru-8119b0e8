// Sarvam TTS proxy — keeps SARVAM_API_KEY server-side.
// POST { text, target_language_code, speaker? } -> { audio: base64 }
import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech";

// Sarvam expects BCP-47 with `-IN` suffix for Indic languages.
const toSarvamLang = (code: string): string => {
  if (!code) return "en-IN";
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
    // Auth — every caller must be a signed-in user.
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
    const { data: claims, error: claimErr } = await supabase.auth.getClaims(
      authHeader.replace("Bearer ", ""),
    );
    if (claimErr || !claims?.claims) {
      return new Response(JSON.stringify({ error: "Unauthorized" }), {
        status: 401, headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const body = await req.json().catch(() => null);
    const text = typeof body?.text === "string" ? body.text.slice(0, 4000) : "";
    const lang = toSarvamLang(String(body?.target_language_code ?? "en"));
    const speaker = typeof body?.speaker === "string" ? body.speaker : "anushka";
    if (!text.trim()) {
      return new Response(JSON.stringify({ error: "text required" }), {
        status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const apiKey = Deno.env.get("SARVAM_API_KEY");
    if (!apiKey) {
      return new Response(JSON.stringify({ error: "TTS not configured" }), {
        status: 503, headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const sarvamRes = await fetch(SARVAM_TTS_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "api-subscription-key": apiKey,
      },
      body: JSON.stringify({
        inputs: [text],
        target_language_code: lang,
        speaker,
        model: "bulbul:v2",
        speech_sample_rate: 22050,
        enable_preprocessing: true,
      }),
    });

    if (!sarvamRes.ok) {
      const errText = await sarvamRes.text();
      console.error("Sarvam TTS error", sarvamRes.status, errText);
      return new Response(
        JSON.stringify({ error: "TTS upstream failed", status: sarvamRes.status }),
        { status: 502, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    const data = await sarvamRes.json();
    const audio = Array.isArray(data?.audios) ? data.audios[0] : data?.audio;
    if (!audio) {
      return new Response(JSON.stringify({ error: "No audio in upstream response" }), {
        status: 502, headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    return new Response(JSON.stringify({ audio }), {
      status: 200,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (e) {
    console.error("sarvam-tts crash", e);
    return new Response(
      JSON.stringify({ error: "An internal error occurred. Please try again." }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }
});
