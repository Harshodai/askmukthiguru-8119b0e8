// Eval runner — executes active golden_questions via Lovable AI, judges faithfulness,
// writes eval_runs + eval_results. Admin only.
import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

const ANSWER_SYSTEM = `You are Sri Preethaji & Sri Krishnaji's spiritual guide.
Answer the seeker's question briefly (2-4 sentences) drawing on the teachings of the Beautiful State.`;

const JUDGE_SYSTEM = `You evaluate a spiritual guide's answer against an expected answer.
Return ONLY compact JSON: {"faithfulness":0..1,"answer_relevancy":0..1,"context_precision":0..1,"context_recall":0..1,"passed":boolean,"reason":"..."}.
No prose, no code fences.`;

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  try {
    const authHeader = req.headers.get("Authorization");
    if (!authHeader?.startsWith("Bearer ")) return json({ error: "Unauthorized" }, 401);

    const userClient = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_ANON_KEY")!,
      { global: { headers: { Authorization: authHeader } } },
    );
    const token = authHeader.replace("Bearer ", "");
    const { data: claims } = await userClient.auth.getClaims(token);
    if (!claims?.claims?.sub) return json({ error: "Unauthorized" }, 401);
    const { data: isAdmin } = await userClient.rpc("has_role", {
      _user_id: claims.claims.sub,
      _role: "admin",
    });
    if (!isAdmin) return json({ error: "Forbidden" }, 403);

    const admin = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    );
    const LOVABLE_API_KEY = Deno.env.get("LOVABLE_API_KEY")!;

    const { data: questions, error: qErr } = await admin
      .from("golden_questions")
      .select("id, question, expected_answer, tags")
      .eq("active", true)
      .limit(25);
    if (qErr) return json({ error: qErr.message }, 500);
    if (!questions?.length) return json({ error: "No active golden questions" }, 400);

    const body = await req.json().catch(() => ({}));
    const runName = body.name ?? `Manual eval ${new Date().toISOString()}`;

    const { data: run, error: runErr } = await admin
      .from("eval_runs")
      .insert({
        name: runName,
        status: "running",
        triggered_by: "manual",
        summary: {},
      })
      .select()
      .single();
    if (runErr) return json({ error: runErr.message }, 500);

    let passed = 0;
    let sumF = 0, sumR = 0, sumCp = 0, sumCr = 0;
    const results: Array<Record<string, unknown>> = [];

    for (const q of questions) {
      const answerResp = await callAI(LOVABLE_API_KEY, [
        { role: "system", content: ANSWER_SYSTEM },
        { role: "user", content: q.question },
      ]);
      const answer = answerResp?.choices?.[0]?.message?.content ?? "";

      const judgeResp = await callAI(LOVABLE_API_KEY, [
        { role: "system", content: JUDGE_SYSTEM },
        {
          role: "user",
          content: JSON.stringify({
            question: q.question,
            expected: q.expected_answer ?? "",
            answer,
          }),
        },
      ]);
      const judgeText = judgeResp?.choices?.[0]?.message?.content ?? "{}";
      let metrics: Record<string, number | boolean | string> = {};
      try {
        metrics = JSON.parse(judgeText.replace(/```json|```/g, "").trim());
      } catch {
        metrics = { faithfulness: 0, answer_relevancy: 0, context_precision: 0, context_recall: 0, passed: false, reason: "parse error" };
      }
      const f = Number(metrics.faithfulness ?? 0);
      const r = Number(metrics.answer_relevancy ?? 0);
      const cp = Number(metrics.context_precision ?? 0);
      const cr = Number(metrics.context_recall ?? 0);
      const ok = Boolean(metrics.passed) || f >= 0.7;
      if (ok) passed++;
      sumF += f; sumR += r; sumCp += cp; sumCr += cr;

      results.push({
        run_id: run.id,
        question: q.question,
        answer,
        score: f,
        metrics,
      });
    }

    await admin.from("eval_results").insert(results);

    const n = questions.length;
    const summary = {
      total: n,
      passed,
      avg_faithfulness: sumF / n,
      avg_answer_relevancy: sumR / n,
      avg_context_precision: sumCp / n,
      avg_context_recall: sumCr / n,
    };

    await admin
      .from("eval_runs")
      .update({ status: "ok", summary, finished_at: new Date().toISOString() })
      .eq("id", run.id);

    return json({ ok: true, run_id: run.id, summary });
  } catch (e) {
    return json({ error: e instanceof Error ? e.message : "unknown" }, 500);
  }
});

async function callAI(apiKey: string, messages: Array<{ role: string; content: string }>) {
  const r = await fetch("https://ai.gateway.lovable.dev/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Lovable-API-Key": apiKey },
    body: JSON.stringify({ model: "google/gemini-2.5-flash", messages }),
  });
  if (!r.ok) throw new Error(`AI ${r.status}: ${await r.text()}`);
  return r.json();
}

function json(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}
