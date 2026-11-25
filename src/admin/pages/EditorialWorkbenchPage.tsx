import { useState } from "react";
import { BookOpen, CheckCircle2, FileSearch, FileText, Lightbulb, ShieldAlert, Sparkles } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fetchWithAuth } from "@/admin/lib/api";

interface EvidenceItem {
  evidence_id: string;
  source_title: string;
  source_url: string;
  source_type: string;
  teacher_id?: string | null;
  start_time?: number | null;
  page_number?: number | null;
  text: string;
  corroborating_sources?: string[];
}

interface DossierResponse {
  dossier_id: string;
  topic: string;
  existing_coverage_count: number;
  teacher_coverage: Record<string, number>;
  source_type_coverage: Record<string, number>;
  underexplored_angles: string[];
  evidence_items: EvidenceItem[];
  lane_errors?: string[];
}

interface OpportunityItem {
  topic: string;
  opportunity_type: string;
  seeker_query_count: number;
  abstain_rate: number;
  indexed_evidence_count: number;
  ingestion_completeness_note: string;
  rationale: string;
  proposed_angle: string;
}

interface ScriptBlock {
  block_id: string;
  block_type: "exact_quote" | "faithful_paraphrase" | "editorial_narration" | "ai_explanation" | "proposed_connection";
  text: string;
  teacher_attributed?: string | null;
  evidence_ids: string[];
}

interface FactCheckResponse {
  passed: boolean;
  unsupported_count: number;
  misattributed_count: number;
  quote_mismatch_count: number;
  summary: string;
}

interface BriefSummary {
  brief_id: string;
  core_thesis: string;
  differentiating_angle: string;
  primary_evidence_ids: string[];
}

interface OutlineSectionSummary {
  order: number;
  heading: string;
  epistemic_role: string;
  notes: string;
}

interface EditorialProject {
  project_id: string;
  title: string;
  topic: string;
  status: string;
  approved_by?: string | null;
  brief?: BriefSummary | null;
  outline?: { outline_id: string; sections: OutlineSectionSummary[] } | null;
}

export default function EditorialWorkbenchPage() {
  const [topic, setTopic] = useState("Dissolving suffering and emotional hurt");
  const [objective, setObjective] = useState("Create a deeply sourced 10-minute teaching exploration");
  const [teacherScope, setTeacherScope] = useState("");
  const [dossier, setDossier] = useState<DossierResponse | null>(null);
  const [opportunities, setOpportunities] = useState<OpportunityItem[]>([]);
  const [scriptText, setScriptText] = useState("");
  const [blockType, setBlockType] = useState<ScriptBlock["block_type"]>("exact_quote");
  const [attributedTeacher, setAttributedTeacher] = useState("preethaji");
  const [selectedEvidenceId, setSelectedEvidenceId] = useState("");
  const [factCheck, setFactCheck] = useState<FactCheckResponse | null>(null);
  const [activeProject, setActiveProject] = useState<EditorialProject | null>(null);
  const [approvalNotes, setApprovalNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runResearch = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWithAuth<DossierResponse>("/api/editorial/research", {
        method: "POST",
        body: JSON.stringify({
          topic,
          objective,
          teacher_scope: teacherScope || null,
          max_evidence: 15,
        }),
      });
      setDossier(res);
      if (res.lane_errors && res.lane_errors.length > 0) {
        setError(`Some evidence lanes failed: ${res.lane_errors.join("; ")}`);
      }
      if (res.evidence_items.length > 0) {
        setSelectedEvidenceId(res.evidence_items[0].evidence_id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate research dossier");
    } finally {
      setLoading(false);
    }
  };

  const loadOpportunities = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWithAuth<{ opportunities: OpportunityItem[] }>("/api/editorial/opportunities", {
        method: "POST",
      });
      setOpportunities(res.opportunities || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load content opportunities");
    } finally {
      setLoading(false);
    }
  };

  const runFactCheck = async () => {
    if (!dossier) return;
    setLoading(true);
    setError(null);
    try {
      const block: ScriptBlock = {
        block_id: "b1",
        block_type: blockType,
        text: scriptText,
        teacher_attributed: blockType === "editorial_narration" ? null : attributedTeacher || null,
        evidence_ids: selectedEvidenceId ? [selectedEvidenceId] : [],
      };
      const res = await fetchWithAuth<FactCheckResponse>("/api/editorial/fact-check", {
        method: "POST",
        body: JSON.stringify({
          blocks: [block],
          evidence_pool: dossier.evidence_items,
        }),
      });
      setFactCheck(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fact-check failed");
    } finally {
      setLoading(false);
    }
  };

  const createAndBuildProjectBrief = async () => {
    setLoading(true);
    setError(null);
    try {
      const created = await fetchWithAuth<EditorialProject>("/api/editorial/projects", {
        method: "POST",
        body: JSON.stringify({ title: topic, topic, objective }),
      });
      await fetchWithAuth<EditorialProject>(`/api/editorial/projects/${created.project_id}/dossier`, {
        method: "POST",
        body: JSON.stringify({ topic, objective, teacher_scope: teacherScope || null, max_evidence: 15 }),
      });
      await fetchWithAuth<EditorialProject>(`/api/editorial/projects/${created.project_id}/brief`, {
        method: "POST",
      });
      const outlined = await fetchWithAuth<EditorialProject>(`/api/editorial/projects/${created.project_id}/outline`, {
        method: "POST",
      });
      setActiveProject(outlined);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create editorial brief & outline");
    } finally {
      setLoading(false);
    }
  };

  const attachAndApproveProject = async () => {
    if (!activeProject || !dossier) return;
    setLoading(true);
    setError(null);
    try {
      const block: ScriptBlock = {
        block_id: "b1",
        block_type: blockType,
        text: scriptText,
        teacher_attributed: blockType === "editorial_narration" ? null : attributedTeacher || null,
        evidence_ids: selectedEvidenceId ? [selectedEvidenceId] : [],
      };
      await fetchWithAuth<EditorialProject>(`/api/editorial/projects/${activeProject.project_id}/script`, {
        method: "POST",
        body: JSON.stringify({
          title: activeProject.title,
          topic: activeProject.topic,
          blocks: [block],
          evidence_pool: dossier.evidence_items,
        }),
      });
      const approved = await fetchWithAuth<EditorialProject>(`/api/editorial/projects/${activeProject.project_id}/approve`, {
        method: "POST",
        body: JSON.stringify({ notes: approvalNotes || "Human verified against canonical evidence" }),
      });
      setActiveProject(approved);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Approval blocked by verification gate");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Editorial Intelligence Workbench</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Source-grounded research dossiers, content gap discovery, and claim-verified scripts requiring human approval.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <Tabs defaultValue="research">
        <TabsList>
          <TabsTrigger value="research" className="gap-1.5">
            <FileSearch className="h-4 w-4" /> Research Dossier
          </TabsTrigger>
          <TabsTrigger value="opportunities" className="gap-1.5" onClick={loadOpportunities}>
            <Lightbulb className="h-4 w-4" /> Content Opportunities
          </TabsTrigger>
          <TabsTrigger value="script" className="gap-1.5">
            <FileText className="h-4 w-4" /> Script & Fact-Check
          </TabsTrigger>
        </TabsList>

        <TabsContent value="research" className="space-y-4 mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Generate Sourced Research Dossier</CardTitle>
              <CardDescription>
                Fuses Qdrant passages, Memgraph concept neighborhoods, and verified source metadata.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-3 md:grid-cols-3">
                <Input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Editorial topic" />
                <Input value={objective} onChange={(e) => setObjective(e.target.value)} placeholder="Editorial objective" />
                <Input value={teacherScope} onChange={(e) => setTeacherScope(e.target.value)} placeholder="Teacher scope (optional: preethaji | krishnaji)" />
              </div>
              <Button onClick={runResearch} disabled={loading}>
                <Sparkles className="h-4 w-4 mr-2" />
                {loading ? "Researching Corpus..." : "Build Research Dossier"}
              </Button>
            </CardContent>
          </Card>

          {dossier && (
            <div className="grid gap-4 md:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Coverage & Underexplored Angles</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="secondary">Sources: {dossier.existing_coverage_count}</Badge>
                    {Object.entries(dossier.teacher_coverage).map(([t, c]) => (
                      <Badge key={t} variant="outline">{t}: {c}</Badge>
                    ))}
                    {Object.entries(dossier.source_type_coverage).map(([st, c]) => (
                      <Badge key={st} variant="outline">{st}: {c}</Badge>
                    ))}
                  </div>
                  <ul className="list-disc pl-5 space-y-1 text-muted-foreground">
                    {dossier.underexplored_angles.map((a, idx) => (
                      <li key={idx}>{a}</li>
                    ))}
                  </ul>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Verified Evidence & Timestamps ({dossier.evidence_items.length})</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 max-h-[420px] overflow-y-auto">
                  {dossier.evidence_items.map((ev) => (
                    <div key={ev.evidence_id} className="rounded-md border p-3 space-y-1.5 text-sm">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium truncate">{ev.source_title || ev.source_url}</span>
                        <div className="flex items-center gap-1 shrink-0">
                          <Badge variant="outline">{ev.teacher_id || "shared"}</Badge>
                          {ev.start_time != null && <Badge variant="secondary">{Math.floor(ev.start_time)}s</Badge>}
                          {ev.page_number != null && <Badge variant="secondary"><BookOpen className="h-3 w-3 mr-1" />p.{ev.page_number}</Badge>}
                        </div>
                      </div>
                      <p className="text-muted-foreground text-xs leading-relaxed">{ev.text}</p>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>

        <TabsContent value="opportunities" className="space-y-4 mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Content Gap & Opportunity Discovery</CardTitle>
              <CardDescription>
                Distinguishes true corpus gaps from uningested books or talks.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {opportunities.length === 0 ? (
                <p className="text-sm text-muted-foreground">No seeker demand clusters loaded yet.</p>
              ) : (
                opportunities.map((o, idx) => (
                  <div key={idx} className="rounded-md border p-3 space-y-1 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{o.topic}</span>
                      <Badge>{o.opportunity_type}</Badge>
                    </div>
                    <p className="text-muted-foreground text-xs">{o.rationale}</p>
                    <p className="text-xs text-amber-600 dark:text-amber-400">{o.ingestion_completeness_note}</p>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="script" className="space-y-4 mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Claim-to-Evidence Script Validator</CardTitle>
              <CardDescription>
                Verifies exact quotations and teacher attribution against dossier evidence before human approval.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-3 md:grid-cols-3">
                <select
                  className="rounded-md border bg-background px-3 py-2 text-sm"
                  value={blockType}
                  onChange={(e) => setBlockType(e.target.value as ScriptBlock["block_type"])}
                >
                  <option value="exact_quote">Exact Teacher Quotation</option>
                  <option value="faithful_paraphrase">Faithful Paraphrase</option>
                  <option value="editorial_narration">Editorial Narration</option>
                  <option value="ai_explanation">AI Explanation</option>
                  <option value="proposed_connection">Proposed Connection</option>
                </select>
                <Input value={attributedTeacher} onChange={(e) => setAttributedTeacher(e.target.value)} placeholder="Attributed teacher" />
                <Input value={selectedEvidenceId} onChange={(e) => setSelectedEvidenceId(e.target.value)} placeholder="Evidence ID" />
              </div>
              <Textarea
                rows={4}
                value={scriptText}
                onChange={(e) => setScriptText(e.target.value)}
                placeholder="Paste script segment or quotation to verify against the dossier..."
              />
              <div className="flex flex-wrap gap-2">
                <Button onClick={runFactCheck} disabled={loading || !dossier}>
                  Verify Claim & Attribution
                </Button>
                <Button variant="outline" onClick={createAndBuildProjectBrief} disabled={loading}>
                  Create Project, Brief & Outline
                </Button>
                <Button variant="secondary" onClick={attachAndApproveProject} disabled={loading || !activeProject || !dossier}>
                  Human Approve Script
                </Button>
              </div>
              <Input
                value={approvalNotes}
                onChange={(e) => setApprovalNotes(e.target.value)}
                placeholder="Human reviewer approval notes (required audit record)"
              />

              {activeProject && (
                <div className="rounded-md border p-3 space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">Project: {activeProject.title}</span>
                    <Badge variant={activeProject.status === "approved" ? "default" : "secondary"}>
                      {activeProject.status}
                    </Badge>
                  </div>
                  {activeProject.brief && (
                    <p className="text-muted-foreground">Brief Angle: {activeProject.brief.differentiating_angle}</p>
                  )}
                  {activeProject.outline && (
                    <ul className="list-disc pl-4 text-muted-foreground">
                      {activeProject.outline.sections.map((s) => (
                        <li key={s.order}>
                          [{s.epistemic_role}] {s.heading}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {factCheck && (
                <div className="rounded-md border p-3 flex items-center gap-2 text-sm">
                  {factCheck.passed ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                  ) : (
                    <ShieldAlert className="h-4 w-4 text-destructive" />
                  )}
                  <span>{factCheck.summary}</span>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
