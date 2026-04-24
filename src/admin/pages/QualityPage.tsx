import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import {
  useQuality,
  useSafetyEvents,
  useAnnotations,
} from "@/admin/hooks/useAdminData";
import { fmtDateTime, fmtPct, truncate } from "@/admin/lib/formatters";
import { EmptyState } from "@/admin/components/EmptyState";

export default function QualityPage() {
  const { data: quality } = useQuality();
  const { data: safety } = useSafetyEvents();
  const { data: annos } = useAnnotations();

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Quality</h1>
        <p className="text-sm text-muted-foreground">
          RAGAS scores, judge↔user disagreement, safety events, annotations.
        </p>
      </div>

      <Tabs defaultValue="disagreement">
        <TabsList>
          <TabsTrigger value="disagreement">Disagreement queue</TabsTrigger>
          <TabsTrigger value="lowconf">Low confidence</TabsTrigger>
          <TabsTrigger value="safety">Safety</TabsTrigger>
          <TabsTrigger value="anno">Annotations</TabsTrigger>
        </TabsList>

        <TabsContent value="disagreement">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Where the judge and the user disagree
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {!quality?.disagreements.length ? (
                <EmptyState title="No disagreements in this window" />
              ) : (
                quality.disagreements.map((d) => (
                  <div
                    key={d.id}
                    className="border border-border rounded-md p-3 text-sm space-y-1"
                  >
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={
                          d.kind === "judge_good_user_bad" ? "destructive" : "secondary"
                        }
                      >
                        {d.kind === "judge_good_user_bad"
                          ? "judge OK · user 👎"
                          : "judge ⚠ · user 👍"}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        Faithfulness {fmtPct(d.faithfulness)}
                      </span>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {truncate(d.response_text, 160)}
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="lowconf">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Low-confidence responses</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {!quality?.low_confidence.length ? (
                <EmptyState title="No low-confidence responses" />
              ) : (
                quality.low_confidence.map((r) => (
                  <div
                    key={r.id}
                    className="border border-border rounded-md p-3 text-sm flex items-center gap-3"
                  >
                    <Badge variant="outline">{fmtPct(r.confidence)}</Badge>
                    <span className="flex-1 text-xs">{truncate(r.response_text, 120)}</span>
                    <span className="text-xs text-muted-foreground">
                      {fmtDateTime(r.created_at)}
                    </span>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="safety">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Safety events</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {!safety?.length ? (
                <EmptyState title="No safety events in this window" />
              ) : (
                safety.map((e) => (
                  <div
                    key={e.id}
                    className="border border-border rounded-md p-3 text-sm flex items-center gap-3"
                  >
                    <Badge
                      variant={
                        e.severity === "high"
                          ? "destructive"
                          : e.severity === "medium"
                            ? "secondary"
                            : "outline"
                      }
                    >
                      {e.severity}
                    </Badge>
                    <Badge variant="outline">{e.type}</Badge>
                    <span className="flex-1 text-xs italic">"{truncate(e.excerpt, 100)}"</span>
                    <span className="text-xs text-muted-foreground">
                      {fmtDateTime(e.created_at)}
                    </span>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="anno">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Reviewer annotations</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {!annos?.length ? (
                <EmptyState title="No annotations yet" />
              ) : (
                annos.map((a) => (
                  <div
                    key={a.id}
                    className="border border-border rounded-md p-3 text-sm flex items-center gap-3"
                  >
                    <Badge
                      variant={
                        a.label === "good"
                          ? "secondary"
                          : a.label === "bad"
                            ? "destructive"
                            : "outline"
                      }
                    >
                      {a.label}
                    </Badge>
                    <span className="flex-1 text-xs">{a.notes}</span>
                    {a.promoted_to_golden && <Badge variant="outline">→ golden</Badge>}
                    <span className="text-xs text-muted-foreground">
                      {fmtDateTime(a.created_at)}
                    </span>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
