import React, { useState, useMemo } from 'react';
import {
  Sparkles,
  Shield,
  ShieldCheck,
  Copy,
  Check,
  ExternalLink,
  Clock,
  Cpu,
  Layers,
  Info,
  FileCode,
  Activity,
  BookOpen
} from 'lucide-react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription
} from '@/components/ui/sheet';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useToast } from '@/hooks/use-toast';
import { cn } from '@/lib/utils';
import type { Message } from '@/lib/chatStorage';
import {
  type AIProvenanceManifest,
  type OriginType,
  createProvenanceManifestFromMessage,
  generateProvOJsonLd
} from '@/types/provenance';

export interface ProvenanceDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  manifest?: AIProvenanceManifest | null;
  message?: Message | null;
}

export const ProvenanceDrawer: React.FC<ProvenanceDrawerProps> = ({
  isOpen,
  onClose,
  manifest: explicitManifest,
  message,
}) => {
  const { toast } = useToast();
  const [copied, setCopied] = useState(false);
  const [showRawJson, setShowRawJson] = useState(false);

  const manifest: AIProvenanceManifest = useMemo(() => {
    if (explicitManifest) return explicitManifest;
    if (message) return createProvenanceManifestFromMessage(message);
    return createProvenanceManifestFromMessage({
      id: 'default-manifest',
      role: 'guru',
      content: '',
      timestamp: new Date(),
    });
  }, [explicitManifest, message]);

  const jsonLdData = useMemo(() => {
    return manifest.jsonLd || generateProvOJsonLd(manifest);
  }, [manifest]);

  const jsonLdString = useMemo(() => {
    return JSON.stringify(jsonLdData, null, 2);
  }, [jsonLdData]);

  const handleCopyJsonLd = async () => {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(jsonLdString);
      } else {
        const textarea = document.createElement('textarea');
        textarea.value = jsonLdString;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
      }
      setCopied(true);
      toast({
        title: 'Machine-Readable Provenance Copied',
        description: 'W3C PROV-O JSON-LD manifest copied to clipboard.',
      });
      setTimeout(() => setCopied(false), 2500);
    } catch {
      toast({
        title: 'Failed to copy',
        description: 'Could not write provenance manifest to clipboard.',
        variant: 'destructive',
      });
    }
  };

  const originSteps: Array<{ type: OriginType; label: string; desc: string }> = [
    { type: 'human_generated', label: 'Human', desc: 'Directly authored by humans' },
    { type: 'ai_assisted', label: 'AI Assisted', desc: 'Human supervised with AI enhancement' },
    { type: 'ai_generated', label: 'AI Generated', desc: 'Synthesized by AI foundation model' },
  ];

  const currentOriginIndex = originSteps.findIndex((s) => s.type === manifest.originType);
  const activeOriginIndex = currentOriginIndex >= 0 ? currentOriginIndex : 2;

  const formattedDate = useMemo(() => {
    try {
      const d = new Date(manifest.generatedAt);
      return new Intl.DateTimeFormat('en-US', {
        dateStyle: 'medium',
        timeStyle: 'medium',
      }).format(d);
    } catch {
      return manifest.generatedAt;
    }
  }, [manifest.generatedAt]);

  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-lg p-0 flex flex-col bg-card border-l border-border/80 shadow-2xl"
        data-testid="provenance-drawer"
      >
        <SheetHeader className="px-5 pt-5 pb-4 border-b border-border/60 flex-shrink-0 bg-muted/20">
          <div className="flex items-center gap-2 text-ojas">
            <ShieldCheck className="w-5 h-5 text-ojas" aria-hidden="true" />
            <SheetTitle className="text-base sm:text-lg font-serif font-medium tracking-tight text-foreground">
              AI Provenance & Disclosure
            </SheetTitle>
          </div>
          <SheetDescription className="text-xs text-muted-foreground mt-1">
            EU Artificial Intelligence Act (Regulation 2024/1689) Article 50 Transparency Specification & Machine-Readable Lineage
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="flex-1 px-5 py-4 pb-[calc(1.5rem+env(safe-area-inset-bottom,0px))]">
          <div className="space-y-5">
            {/* 1. Article 50 Plain Language Disclosure Box */}
            <div className="rounded-xl border border-ojas/25 bg-gradient-to-br from-ojas/10 via-card to-background p-4 shadow-sm">
              <div className="flex items-start gap-3">
                <div className="p-1.5 rounded-lg bg-ojas/15 text-ojas shrink-0 mt-0.5">
                  <Sparkles className="w-4 h-4" aria-hidden="true" />
                </div>
                <div className="space-y-1 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-ojas tracking-wide uppercase text-[10.5px]">
                      Article 50(1) Transparency Notice
                    </span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-ojas/15 font-medium text-ojas">
                      Tier: {manifest.riskTier}
                    </span>
                  </div>
                  <p className="text-foreground/90 font-medium leading-relaxed">
                    {manifest.disclosure.plainLanguageDisclosure}
                  </p>
                </div>
              </div>
            </div>

            {/* 2. Origin Classification Visual Meter */}
            <div className="rounded-xl border border-border/70 bg-background/60 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <Layers className="w-3.5 h-3.5 text-ojas" />
                  Origin Classification Meter
                </span>
                <span className="text-xs font-semibold text-ojas bg-ojas/10 px-2.5 py-0.5 rounded-full border border-ojas/20">
                  {originSteps[activeOriginIndex]?.label}
                </span>
              </div>

              {/* Step indicator */}
              <div className="grid grid-cols-3 gap-2 pt-1">
                {originSteps.map((step, idx) => {
                  const isActive = idx === activeOriginIndex;
                  return (
                    <div
                      key={step.type}
                      className={cn(
                        'rounded-lg p-2.5 text-center transition-all border flex flex-col items-center justify-center gap-1',
                        isActive
                          ? 'border-ojas/60 bg-ojas/15 shadow-[0_0_10px_rgba(217,119,6,0.15)] text-foreground font-semibold'
                          : 'border-border/40 bg-muted/20 text-muted-foreground/70 opacity-60'
                      )}
                    >
                      <span className="text-[11px] leading-tight font-medium">{step.label}</span>
                      <span className="text-[9.5px] leading-tight text-muted-foreground line-clamp-1">
                        {step.type === manifest.originType ? 'Active' : ''}
                      </span>
                    </div>
                  );
                })}
              </div>
              <p className="text-[11px] text-muted-foreground/80 leading-normal">
                {originSteps[activeOriginIndex]?.desc} (Modality: {manifest.modality}).
              </p>
            </div>

            {/* 3. Model Descriptor, Latency & Timestamp */}
            <div className="rounded-xl border border-border/70 bg-background/60 p-4 space-y-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <Cpu className="w-3.5 h-3.5 text-ojas" />
                Inference System & Telemetry
              </span>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div className="p-2.5 rounded-lg bg-muted/20 border border-border/40 space-y-1">
                  <span className="text-[10px] uppercase text-muted-foreground font-medium block">Model Ensemble</span>
                  <span className="font-semibold text-foreground truncate block" title={manifest.modelDescriptor.name}>
                    {manifest.modelDescriptor.name}
                  </span>
                  {manifest.modelDescriptor.version && (
                    <span className="text-[10.5px] text-muted-foreground block">{manifest.modelDescriptor.version}</span>
                  )}
                </div>

                <div className="p-2.5 rounded-lg bg-muted/20 border border-border/40 space-y-1">
                  <span className="text-[10px] uppercase text-muted-foreground font-medium block">Provider / System</span>
                  <span className="font-medium text-foreground truncate block">
                    {manifest.modelDescriptor.provider || 'AskMukthiGuru Platform'}
                  </span>
                  <span className="text-[10.5px] text-muted-foreground block">
                    {manifest.modelDescriptor.parameters || 'BGE-M3 + GraphRAG'}
                  </span>
                </div>

                <div className="p-2.5 rounded-lg bg-muted/20 border border-border/40 space-y-1">
                  <span className="text-[10px] uppercase text-muted-foreground font-medium flex items-center gap-1">
                    <Clock className="w-3 h-3 text-ojas" />
                    Timestamp
                  </span>
                  <span className="font-medium text-foreground block">{formattedDate}</span>
                </div>

                <div className="p-2.5 rounded-lg bg-muted/20 border border-border/40 space-y-1">
                  <span className="text-[10px] uppercase text-muted-foreground font-medium flex items-center gap-1">
                    <Activity className="w-3 h-3 text-ojas" />
                    Latency & Duration
                  </span>
                  <span className="font-medium text-foreground block">
                    {manifest.latencyMs ? `${manifest.latencyMs} ms` : 'Streaming realtime (< 1s)'}
                  </span>
                </div>
              </div>
            </div>

            {/* 4. Grounding Status & Source Verification */}
            <div className="rounded-xl border border-border/70 bg-background/60 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <BookOpen className="w-3.5 h-3.5 text-ojas" />
                  Knowledge Grounding Lineage
                </span>
                <span
                  className={cn(
                    'text-[11px] px-2.5 py-0.5 rounded-full font-medium border capitalize',
                    manifest.grounding.status === 'grounded'
                      ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                      : 'border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400'
                  )}
                >
                  {manifest.grounding.status.replace('_', ' ')}
                </span>
              </div>

              <div className="p-3 rounded-lg bg-muted/20 border border-border/40 space-y-2 text-xs">
                <div className="flex justify-between items-center text-xs">
                  <span className="text-muted-foreground">Corpus Grounding:</span>
                  <span className="font-medium text-foreground">
                    {manifest.grounding.evidenceSupportLabel || 'Dual-Layer Doctrine Retrieval'}
                  </span>
                </div>
                <div className="flex justify-between items-center text-xs">
                  <span className="text-muted-foreground">Source Citations:</span>
                  <span className="font-medium text-foreground">
                    {manifest.grounding.sourceCount} verified {manifest.grounding.sourceCount === 1 ? 'source' : 'sources'}
                  </span>
                </div>
                {typeof manifest.grounding.confidenceScore === 'number' && (
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-muted-foreground">Confidence Score:</span>
                    <span className="font-medium text-foreground">
                      {(manifest.grounding.confidenceScore * 100).toFixed(0)}%
                    </span>
                  </div>
                )}
                {manifest.grounding.corpusVersion && (
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-muted-foreground">Corpus Version:</span>
                    <span className="font-mono text-[11px] text-muted-foreground">
                      {manifest.grounding.corpusVersion}
                    </span>
                  </div>
                )}
              </div>

              {/* Source list if citations exist */}
              {manifest.grounding.sources && manifest.grounding.sources.length > 0 && (
                <div className="space-y-1.5 pt-1">
                  <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">
                    Retrieved Knowledge Documents
                  </p>
                  <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
                    {manifest.grounding.sources.map((src, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between p-2 rounded-md bg-muted/30 border border-border/40 text-xs"
                      >
                        <span className="truncate max-w-[280px] font-medium text-foreground/90">
                          {src.title || `Source ${i + 1}`}
                        </span>
                        {src.url && (
                          <a
                            href={src.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-ojas hover:underline flex items-center gap-1 shrink-0 ml-2"
                          >
                            <span className="text-[11px]">View</span>
                            <ExternalLink className="w-3 h-3" />
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {manifest.grounding.evidenceBands
                && Object.values(manifest.grounding.evidenceBands).some((items) => items.length > 0) && (
                <div className="space-y-2 pt-1" data-testid="provenance-evidence-bands">
                  <div className="flex items-center justify-between">
                    <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">
                      Graph & Source Evidence Bands
                    </p>
                    {typeof manifest.grounding.evidenceCount === 'number' && (
                      <span className="text-[10px] text-muted-foreground">
                        {manifest.grounding.evidenceCount} evidence items
                      </span>
                    )}
                  </div>
                  {manifest.grounding.entitiesTouched && manifest.grounding.entitiesTouched.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {manifest.grounding.entitiesTouched.slice(0, 12).map((entity) => (
                        <span key={entity} className="rounded-full border border-ojas/20 bg-ojas/10 px-2 py-0.5 text-[10px] text-ojas">
                          {entity}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                    {Object.entries(manifest.grounding.evidenceBands)
                      .filter(([, items]) => items.length > 0)
                      .map(([band, items]) => (
                        <div key={band} className="rounded-lg border border-border/40 bg-muted/20 p-2.5 space-y-1.5">
                          <p className="text-[10px] font-semibold uppercase tracking-wide text-foreground/80">
                            {band.replaceAll('_', ' ')}
                          </p>
                          {items.slice(0, 4).map((item, index) => (
                            <div key={`${item.source_segment_id || item.source_url || band}-${index}`} className="rounded-md bg-background/60 p-2 text-[11px] space-y-1">
                              <p className="text-foreground/90 leading-relaxed line-clamp-3">{item.text || 'Evidence metadata available'}</p>
                              <div className="flex flex-wrap gap-x-2 gap-y-0.5 text-[10px] text-muted-foreground">
                                {item.relation && <span>relation: {item.relation}</span>}
                                {typeof item.hop === 'number' && item.hop > 0 && <span>hop: {item.hop}</span>}
                                {item.source_segment_id && <span>segment: {item.source_segment_id}</span>}
                                {item.ontology_version && <span>ontology: {item.ontology_version}</span>}
                              </div>
                              {item.source_url && (
                                <a href={item.source_url} target="_blank" rel="noopener noreferrer" className="text-ojas hover:underline inline-flex items-center gap-1">
                                  View source <ExternalLink className="w-3 h-3" />
                                </a>
                              )}
                            </div>
                          ))}
                        </div>
                      ))}
                  </div>
                </div>
              )}
            </div>

            {/* 5. Machine-Readable PROV-O JSON-LD Exporter */}
            <div className="rounded-xl border border-border/70 bg-background/60 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <FileCode className="w-3.5 h-3.5 text-ojas" />
                  Machine-Readable PROV-O JSON-LD
                </span>
                <button
                  type="button"
                  onClick={() => setShowRawJson(!showRawJson)}
                  className="text-[11px] text-ojas hover:underline font-medium focus-visible:outline-none"
                >
                  {showRawJson ? 'Hide Preview' : 'Show Preview'}
                </button>
              </div>

              <p className="text-[11.5px] text-muted-foreground leading-normal">
                Standard W3C PROV-O JSON-LD document compliant with EU AI Act technical documentation and transparency standards.
              </p>

              {showRawJson && (
                <div className="rounded-lg bg-muted/50 p-3 border border-border/50 max-h-48 overflow-auto font-mono text-[10.5px] leading-relaxed text-foreground/80">
                  <pre>{jsonLdString}</pre>
                </div>
              )}

              <button
                type="button"
                onClick={handleCopyJsonLd}
                className={cn(
                  'w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg font-medium text-xs transition-all duration-200 shadow-sm',
                  copied
                    ? 'bg-emerald-600 text-white'
                    : 'bg-ojas hover:bg-ojas-light text-primary-foreground focus-visible:ring-2 focus-visible:ring-ojas/50'
                )}
                aria-label="Copy Machine-Readable PROV-O JSON-LD"
              >
                {copied ? (
                  <>
                    <Check className="w-4 h-4" />
                    <span>Copied PROV-O JSON-LD!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    <span>Copy Machine-Readable PROV-O JSON-LD</span>
                  </>
                )}
              </button>
            </div>

            {/* 6. Regulatory Reference & Safe Harbor */}
            <div className="p-3 rounded-lg bg-muted/30 border border-border/40 text-[11px] text-muted-foreground leading-relaxed flex items-start gap-2">
              <Info className="w-4 h-4 text-muted-foreground/70 shrink-0 mt-0.5" />
              <span>
                EU AI Act Article 50 requires providers of AI systems to ensure that AI-generated content is detectable and marked in a machine-readable format. AskMukthiGuru adheres to responsible, grounded spiritual AI practices.
              </span>
            </div>
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
};
