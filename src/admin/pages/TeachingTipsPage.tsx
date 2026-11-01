import { useCallback, useEffect, useState } from 'react';
import { Quote, RefreshCw, AlertCircle, Plus, Sparkles, Trash2, BookOpen } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  getWisdomTips,
  regenerateWisdomTips,
  getCuratedTeachings,
  addCuratedTeaching,
  deleteCuratedTeaching,
  type WisdomTipsPayload,
  type WisdomTipDto,
} from '@/admin/lib/api';

const daysUntil = (iso?: string | null): number => {
  if (!iso) return 0;
  const time = new Date(iso).getTime();
  if (isNaN(time)) return 0;
  const ms = time - Date.now();
  return Math.max(0, Math.ceil(ms / (24 * 60 * 60 * 1000)));
};

const safeDateTime = (iso?: string | null): string => {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return isNaN(d.getTime()) ? '—' : d.toLocaleString();
  } catch {
    return '—';
  }
};

type LoadState = 'loading' | 'ready' | 'unavailable' | 'error';

export default function TeachingTipsPage() {
  const [payload, setPayload] = useState<WisdomTipsPayload | null>(null);
  const [library, setLibrary] = useState<WisdomTipDto[]>([]);
  const [state, setState] = useState<LoadState>('loading');
  const [regenerating, setRegenerating] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'active' | 'library'>('active');

  // Form state for adding teaching
  const [dialogOpen, setDialogOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formText, setFormText] = useState('');
  const [formTeacher, setFormTeacher] = useState('Sri Preethaji & Sri Krishnaji');
  const [formSource, setFormSource] = useState('The Four Sacred Secrets');
  const [formCategory, setFormCategory] = useState('Beautiful State');

  const load = useCallback(async () => {
    setState('loading');
    try {
      const [tipsData, libraryData] = await Promise.all([
        getWisdomTips(),
        getCuratedTeachings().catch(() => []),
      ]);
      setPayload(tipsData);
      setLibrary(libraryData);
      setState('ready');
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setState(message.includes('404') ? 'unavailable' : 'error');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleRegenerate = async () => {
    setRegenerating(true);
    setStatusMessage(null);
    try {
      const data = await regenerateWisdomTips();
      setPayload(data);
      const lib = await getCuratedTeachings().catch(() => library);
      setLibrary(lib);
      setState('ready');
      const count = (data?.tips ?? []).length;
      setStatusMessage(`Regenerated ${count} tips — updated live across all active user chat sessions.`);
    } catch (err) {
      setStatusMessage(err instanceof Error ? err.message : 'Regeneration failed');
    } finally {
      setRegenerating(false);
    }
  };

  const handleAddTeaching = async () => {
    if (!formText.trim()) return;
    setIsSubmitting(true);
    try {
      await addCuratedTeaching({
        text: formText.trim(),
        teacher: formTeacher,
        source: formSource.trim(),
        category: formCategory.trim(),
      });
      setFormText('');
      setDialogOpen(false);
      await load();
      setStatusMessage('Teaching added to library and propagated to live tips.');
    } catch (err) {
      setStatusMessage(err instanceof Error ? err.message : 'Failed to add teaching');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteTeaching = async (id?: string) => {
    if (!id) return;
    try {
      await deleteCuratedTeaching(id);
      await load();
      setStatusMessage('Teaching removed from curated library.');
    } catch (err) {
      setStatusMessage(err instanceof Error ? err.message : 'Failed to delete teaching');
    }
  };

  const tips = payload?.tips ?? [];
  const previewTip = tips[0] || library[0];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <Quote className="h-6 w-6 text-ojas" />
            <span>Teaching Tips</span>
            <span className="text-muted-foreground text-lg font-normal">— Sacred Guru Wisdom</span>
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Curated aphorisms of Sri Preethaji & Sri Krishnaji shown to seekers in chat while answers are generating.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button size="sm" variant="outline" className="gap-2">
                <Plus className="w-4 h-4" /> Add Teaching
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle>Add Authentic Guru Teaching</DialogTitle>
                <DialogDescription>
                  Enter a verified quote or discourse teaching from Sri Preethaji or Sri Krishnaji.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-foreground">Teaching / Quote</label>
                  <Textarea
                    placeholder="Enter the authentic teaching..."
                    value={formText}
                    onChange={(e) => setFormText(e.target.value)}
                    rows={4}
                    className="resize-none"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-foreground">Teacher</label>
                    <select
                      value={formTeacher}
                      onChange={(e) => setFormTeacher(e.target.value)}
                      className="w-full text-xs rounded-md border border-input bg-background px-3 py-2"
                    >
                      <option value="Sri Preethaji & Sri Krishnaji">Sri Preethaji & Sri Krishnaji</option>
                      <option value="Sri Preethaji">Sri Preethaji</option>
                      <option value="Sri Krishnaji">Sri Krishnaji</option>
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-foreground">Category</label>
                    <Input
                      value={formCategory}
                      onChange={(e) => setFormCategory(e.target.value)}
                      placeholder="e.g. Beautiful State"
                      className="h-8 text-xs"
                    />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-foreground">Source / Discourse</label>
                  <Input
                    value={formSource}
                    onChange={(e) => setFormSource(e.target.value)}
                    placeholder="e.g. The Four Sacred Secrets"
                    className="h-8 text-xs"
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="ghost" onClick={() => setDialogOpen(false)}>Cancel</Button>
                <Button onClick={handleAddTeaching} disabled={isSubmitting || !formText.trim()} className="gap-1.5">
                  <Plus className="w-4 h-4" /> Save & Propagate
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <Button onClick={handleRegenerate} disabled={regenerating} size="sm" className="gap-2">
            <RefreshCw className={`w-4 h-4 ${regenerating ? 'animate-spin' : ''}`} />
            {regenerating ? 'Regenerating…' : 'Regenerate Tips'}
          </Button>
        </div>
      </div>

      {statusMessage && (
        <div className="p-3 bg-ojas/10 border border-ojas/30 rounded-lg text-xs text-ojas font-medium flex items-center justify-between">
          <span>{statusMessage}</span>
          <button onClick={() => setStatusMessage(null)} className="opacity-70 hover:opacity-100 text-xs">Dismiss</button>
        </div>
      )}

      {/* Live Chat Interface Preview Card */}
      {previewTip && (
        <Card className="border-ojas/30 bg-gradient-to-r from-card to-ojas/5">
          <CardHeader className="py-3 px-5 border-b border-border/50">
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-ojas" /> Live Seeker Chat Preview (While Answer Generates)
              </span>
              <Badge variant="secondary" className="text-[10px]">Preview Mode</Badge>
            </div>
          </CardHeader>
          <CardContent className="p-5">
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 space-y-1.5 max-w-2xl">
              <div className="flex items-center gap-2 text-xs font-semibold text-amber-600 dark:text-amber-400">
                <Sparkles className="w-3.5 h-3.5" />
                <span>Sacred Teaching</span>
                <span className="text-muted-foreground font-normal">· {previewTip.teacher}</span>
              </div>
              <p className="font-serif italic text-sm text-foreground/90 leading-relaxed">
                "{previewTip.text}"
              </p>
              {previewTip.source && (
                <div className="text-[11px] text-muted-foreground pt-1 flex items-center gap-2">
                  <span>Source: {previewTip.source}</span>
                  {previewTip.category && <span>· Tag: {previewTip.category}</span>}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Main Tabs */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'active' | 'library')}>
        <div className="flex items-center justify-between border-b border-border pb-2">
          <TabsList className="bg-card border border-border">
            <TabsTrigger value="active" className="gap-2">
              <Quote className="w-3.5 h-3.5" /> Active Rotating Tips ({tips.length})
            </TabsTrigger>
            <TabsTrigger value="library" className="gap-2">
              <BookOpen className="w-3.5 h-3.5" /> Curated Guru Library ({library.length})
            </TabsTrigger>
          </TabsList>
          {payload && activeTab === 'active' && (
            <span className="text-xs text-muted-foreground">
              Expires in {daysUntil(payload.expires_at)}d · Auto-regenerates
            </span>
          )}
        </div>

        <TabsContent value="active" className="mt-4">
          {state === 'loading' && (
            <p className="text-sm text-muted-foreground animate-pulse py-8 text-center">Loading wisdom tips…</p>
          )}
          {state === 'error' && (
            <div className="flex items-center justify-center gap-3 text-sm text-destructive py-8">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>Could not load tips. Check the backend connection.</span>
              <Button variant="outline" size="sm" onClick={() => void load()}>Retry</Button>
            </div>
          )}
          {state === 'ready' && (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {tips.map((tip, idx) => (
                <Card key={tip.id ?? `tip-${idx}`} className="h-full border-ojas/20 flex flex-col justify-between hover:border-ojas/40 transition-all">
                  <CardContent className="pt-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <Badge variant="outline" className="text-[10px] bg-ojas/10 text-ojas border-ojas/30">
                        {tip.category || 'Sacred Wisdom'}
                      </Badge>
                      <span className="text-[10px] text-muted-foreground font-mono">#{idx + 1}</span>
                    </div>
                    <p className="font-serif italic text-sm leading-relaxed text-foreground">
                      "{tip.text ?? ''}"
                    </p>
                    <div className="border-t border-border/50 pt-2 text-[11px] text-muted-foreground">
                      <p className="font-medium text-foreground">🪷 {tip.teacher ?? 'Sri Preethaji & Sri Krishnaji'}</p>
                      {tip.source && <p className="opacity-75 text-[10px] mt-0.5 truncate">{tip.source}</p>}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="library" className="mt-4">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {library.map((item, idx) => (
              <Card key={item.id ?? `lib-${idx}`} className="h-full border-border flex flex-col justify-between hover:border-primary/40 transition-all">
                <CardContent className="pt-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <Badge variant="secondary" className="text-[10px]">
                      {item.category || 'Doctrine'}
                    </Badge>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 text-muted-foreground hover:text-destructive"
                      onClick={() => handleDeleteTeaching(item.id)}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                  <p className="font-serif italic text-sm leading-relaxed text-foreground">
                    "{item.text ?? ''}"
                  </p>
                  <div className="border-t border-border/50 pt-2 text-[11px] text-muted-foreground">
                    <p className="font-medium text-foreground">🪷 {item.teacher}</p>
                    {item.source && <p className="opacity-75 text-[10px] mt-0.5">{item.source}</p>}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

