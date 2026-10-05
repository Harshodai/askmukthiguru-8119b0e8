import React, { useState, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Sparkles,
  Brain,
  Wind,
  Video,
  FileText,
  Sliders,
  ChevronDown,
  X,
  ExternalLink,
  BookOpen,
  Check,
  Compass,
} from 'lucide-react';
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  type Node,
  type Edge,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { useProfile } from '@/hooks/useProfile';
import { useSereneMind } from '@/components/common/SereneMindProvider';
import { memoryApi, type RelevantMemory } from '@/lib/memoryApi';
import { useToast } from '@/hooks/use-toast';
import type { Message } from '@/lib/chatStorage';
import type { Citation } from '@/lib/chat/types';
import type { DiscourseCitation } from './CitationCard';
import { useNavigate } from 'react-router-dom';

export interface DeepenAndTuneBarProps {
  message: Message;
  queryText?: string;
  citation?: Citation | DiscourseCitation | null;
  onOpenVideoModal?: (citation: DiscourseCitation) => void;
  onOpenSearchModal?: (citation: DiscourseCitation) => void;
  className?: string;
}

interface ConceptDefinition {
  name: string;
  category: 'State' | 'Concept' | 'Practice' | 'Doctrine';
  teacher: string;
  relation: string;
  target: string;
  description: string;
}

const CANONICAL_CONCEPTS: ConceptDefinition[] = [
  {
    name: 'Beautiful State',
    category: 'State',
    teacher: 'Sri Preethaji',
    relation: 'cultivates',
    target: 'Witnessing Awareness',
    description: 'A state of connection, peace, and inner expansion where consciousness is free from internal conflict and division.',
  },
  {
    name: 'Shrinking Self',
    category: 'Concept',
    teacher: 'Sri Krishnaji',
    relation: 'dissolves',
    target: 'Suffering State',
    description: 'The contraction of consciousness into obsessive self-concern, defense, and judgment. Recognizing it is the beginning of freedom.',
  },
  {
    name: 'Witnessing Awareness',
    category: 'Practice',
    teacher: 'Sri Preethaji',
    relation: 'transforms into',
    target: 'Inner Stillness',
    description: 'The capacity to observe one\'s thoughts, emotions, and hurts without creating stories, resistance, or self-judgment.',
  },
  {
    name: 'Dissolving Self-Judgment',
    category: 'Practice',
    teacher: 'Sri Preethaji',
    relation: 'leads to',
    target: 'Self-Forgiveness',
    description: 'Dropping the internal civil war of self-condemnation and resting in profound acceptance of who you are.',
  },
  {
    name: 'Heart Connection',
    category: 'State',
    teacher: 'Sri Krishnaji',
    relation: 'overcomes',
    target: 'Loneliness & Division',
    description: 'Experiencing the other not as an object or expectation, but as an interconnected expression of conscious life.',
  },
  {
    name: 'Inner Stillness',
    category: 'State',
    teacher: 'Sri Preethaji',
    relation: 'calms',
    target: 'Agitated Nervous System',
    description: 'The profound quietude that emerges when mental commentary ceases and breathing aligns with the present moment.',
  },
  {
    name: 'Four Sacred Secrets',
    category: 'Doctrine',
    teacher: 'Sri Preethaji & Sri Krishnaji',
    relation: 'guides to',
    target: 'Spiritual Awakening',
    description: 'Foundational roadmap navigating from the suffering state to the beautiful state through spiritual neurobiology.',
  },
  {
    name: 'Atma Vichara',
    category: 'Practice',
    teacher: 'Sri Krishnaji',
    relation: 'awakens',
    target: 'Inner Observer',
    description: 'Direct self-inquiry turning the gaze inward: "Who is the one suffering right now? Can the observer be seen?"',
  },
];

/* Custom micro-graph node */
function MicroWisdomNode({ data }: NodeProps) {
  const accent = data.accent as string || '#f59e0b';
  return (
    <div
      className="relative rounded-2xl border bg-card/95 px-3 py-2.5 shadow-xl backdrop-blur-md min-w-[150px] max-w-[190px] text-center"
      style={{ borderColor: accent }}
    >
      <Handle type="target" position={Position.Top} className="!bg-transparent !border-0" />
      <div className="text-[9px] uppercase tracking-wider font-semibold opacity-75" style={{ color: accent }}>
        {data.category as string}
      </div>
      <div className="mt-0.5 text-xs font-serif font-bold text-foreground truncate">
        {data.label as string}
      </div>
      {Boolean(data.subtext) && (
        <div className="mt-1 text-[10px] text-muted-foreground line-clamp-1">
          {data.subtext as string}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-transparent !border-0" />
    </div>
  );
}

const nodeTypes = {
  microNode: MicroWisdomNode,
};

// The bar receives either a chat Citation (timestampSeconds) or a
// DiscourseCitation (startTimestamp); read whichever field this one has.
const citationStartSeconds = (c: Citation | DiscourseCitation): number | undefined =>
  (c as Partial<Citation>).timestampSeconds ?? (c as Partial<DiscourseCitation>).startTimestamp;

export const DeepenAndTuneBar: React.FC<DeepenAndTuneBarProps> = ({
  message,
  queryText,
  citation,
  onOpenVideoModal,
  onOpenSearchModal,
  className = '',
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { toast } = useToast();
  const { profile, update: updateProfile } = useProfile();
  const { open: openSereneMind } = useSereneMind();

  // Concept Modal State
  const [selectedConcept, setSelectedConcept] = useState<ConceptDefinition | null>(null);

  // Vault Recall State
  const [recallingVault, setRecallingVault] = useState(false);
  const [recalledNotes, setRecalledNotes] = useState<RelevantMemory[]>([]);
  const [showVaultReflection, setShowVaultReflection] = useState(false);

  // Detect relevant concepts for Quadrant A
  const activeConcepts = useMemo<ConceptDefinition[]>(() => {
    const textToScan = `${message.content} ${queryText || ''}`.toLowerCase();
    const matched = CANONICAL_CONCEPTS.filter((c) => {
      const nameParts = c.name.toLowerCase().split(' ');
      return nameParts.some((part) => part.length > 4 && textToScan.includes(part));
    });
    if (matched.length >= 2) return matched.slice(0, 3);
    // Fallback default triad
    return [CANONICAL_CONCEPTS[0], CANONICAL_CONCEPTS[1], CANONICAL_CONCEPTS[2]];
  }, [message.content, queryText]);

  // Current familiarity level
  const currentFamiliarity = profile?.familiarityLevel || 'seeker';

  const handleUpdateFamiliarity = async (level: 'seeker' | 'practitioner' | 'advanced') => {
    try {
      await updateProfile({ familiarityLevel: level });
      const label =
        level === 'advanced'
          ? 'Advanced Meditator'
          : level === 'practitioner'
          ? 'Practitioner'
          : 'Seeker';
      toast({
        title: 'Guidance Tuned',
        description: `Tone depth set to ${label}. Future responses will reflect this depth.`,
      });
    } catch {
      toast({
        title: 'Could not update familiarity',
        variant: 'destructive',
      });
    }
  };

  // Trigger Second Brain Vault Recall
  const handleReflectWithJourney = async () => {
    setRecallingVault(true);
    setShowVaultReflection(true);
    try {
      const searchPrompt = queryText || message.content.slice(0, 200);
      const results = await memoryApi.getRelevant(searchPrompt, 3);
      setRecalledNotes(results);
      if (results.length > 0) {
        toast({
          title: 'Journey Reflections Recalled',
          description: `Found ${results.length} related insight${results.length > 1 ? 's' : ''} from your Second Brain Vault.`,
        });
      }
    } catch (err) {
      console.warn('Vault recall fallback', err);
    } finally {
      setRecallingVault(false);
    }
  };

  // Handle Video and Search Click for Quadrant D
  const handleWatchFullVideo = () => {
    if (!citation || !onOpenVideoModal) return;
    const discourseCitation: DiscourseCitation = {
      index: 1,
      url: citation.url,
      title: citation.title ?? undefined,
      speaker: citation.speaker,
      startTimestamp: citationStartSeconds(citation),
      playbackStartSeconds: citation.playbackStartSeconds,
      playbackEndSeconds: citation.playbackEndSeconds,
    };
    onOpenVideoModal(discourseCitation);
  };

  const handleOpenDiscourseWindow = () => {
    if (!citation || !onOpenSearchModal) return;
    const discourseCitation: DiscourseCitation = {
      index: 1,
      url: citation.url,
      title: citation.title ?? undefined,
      speaker: citation.speaker,
      startTimestamp: citationStartSeconds(citation),
      playbackStartSeconds: citation.playbackStartSeconds,
      playbackEndSeconds: citation.playbackEndSeconds,
    };
    onOpenSearchModal(discourseCitation);
  };

  // Build @xyflow nodes and edges for selected concept
  const { flowNodes, flowEdges } = useMemo(() => {
    if (!selectedConcept) return { flowNodes: [], flowEdges: [] };

    const nodes: Node[] = [
      {
        id: 'teacher',
        type: 'microNode',
        position: { x: 120, y: 20 },
        data: {
          label: selectedConcept.teacher,
          category: 'Teacher',
          subtext: 'Authentic Transmission',
          accent: '#fb7185',
        },
      },
      {
        id: 'concept',
        type: 'microNode',
        position: { x: 120, y: 130 },
        data: {
          label: selectedConcept.name,
          category: selectedConcept.category,
          subtext: 'Core Ontological Entity',
          accent: '#f59e0b',
        },
      },
      {
        id: 'target',
        type: 'microNode',
        position: { x: 120, y: 240 },
        data: {
          label: selectedConcept.target,
          category: 'Outcome / Transformation',
          subtext: 'Somatic Awakening',
          accent: '#34d399',
        },
      },
    ];

    const edges: Edge[] = [
      {
        id: 'e1',
        source: 'teacher',
        target: 'concept',
        label: 'transmits',
        animated: true,
        style: { stroke: '#fb7185', strokeWidth: 2 },
      },
      {
        id: 'e2',
        source: 'concept',
        target: 'target',
        label: selectedConcept.relation,
        animated: true,
        style: { stroke: '#f59e0b', strokeWidth: 2 },
      },
    ];

    return { flowNodes: nodes, flowEdges: edges };
  }, [selectedConcept]);

  return (
    <div
      data-testid="deepen-and-tune-bar"
      className={`mt-4 rounded-2xl border border-saffron-gold/25 bg-card/75 p-3.5 shadow-sm backdrop-blur-md ${className}`}
    >
      {/* Sacred Bar Eyebrow */}
      <div className="flex items-center justify-between pb-2.5 mb-3 border-b border-border/40">
        <div className="flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 text-saffron-gold" />
          <span className="font-serif text-xs font-semibold uppercase tracking-wider text-saffron-gold">
            Deepen & Tune Your Contemplation
          </span>
        </div>
        <span className="text-[10px] text-muted-foreground/80 font-mono">
          Research-Backed Sacred Inquiries
        </span>
      </div>

      {/* 4 Quadrants Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
        {/* Quadrant A: Memgraph GraphRAG (Doctrinal Concept Map) */}
        <div className="flex flex-col justify-between rounded-xl border border-border/40 bg-background/40 p-2.5">
          <div>
            <div className="flex items-center justify-between gap-1 mb-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <Compass className="h-3 w-3 text-amber-500" />
                Pattern A · Memgraph GraphRAG
              </span>
              <span className="text-[9px] font-mono text-amber-500/80 bg-amber-500/10 px-1.5 py-0.5 rounded">
                bolt://memgraph
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground/90 mb-2">
              Ontological concepts extracted from discourse:
            </p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {activeConcepts.map((concept) => (
              <button
                key={concept.name}
                type="button"
                onClick={() => setSelectedConcept(concept)}
                className="inline-flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-600 dark:text-amber-400 hover:bg-amber-500/20 hover:scale-[1.02] transition-all"
                title={`Open Memgraph micro-graph for ${concept.name}`}
              >
                <span className="text-[10px]">◈</span>
                <span>{concept.name}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Quadrant B: Personal Journey & Resonance (Second Brain Vault & Familiarity) */}
        <div className="flex flex-col justify-between rounded-xl border border-border/40 bg-background/40 p-2.5">
          <div>
            <div className="flex items-center justify-between gap-1 mb-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <Brain className="h-3 w-3 text-emerald-500" />
                Pattern B · Journey & Resonance
              </span>
              <span className="text-[9px] font-mono text-emerald-500/80 bg-emerald-500/10 px-1.5 py-0.5 rounded">
                Second Brain Vault
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground/90 mb-2">
              Connect this wisdom with your reflections & tuning:
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleReflectWithJourney}
              className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/20 transition-all"
            >
              <span>🪞</span>
              <span>Reflect with My Journey</span>
            </button>

            {/* Familiarity Dropdown Toggle */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  className="inline-flex items-center gap-1 rounded-xl border border-border/50 bg-background/60 px-2.5 py-1 text-xs font-medium text-foreground hover:bg-muted transition-colors"
                >
                  <Sliders className="h-3 w-3 text-muted-foreground" />
                  <span>
                    Level:{' '}
                    <strong className="capitalize text-saffron-gold">
                      {currentFamiliarity === 'advanced' ? 'Advanced' : currentFamiliarity}
                    </strong>
                  </span>
                  <ChevronDown className="h-3 w-3 text-muted-foreground" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-52">
                <DropdownMenuItem onClick={() => handleUpdateFamiliarity('seeker')}>
                  <div className="flex flex-col text-xs">
                    <span className="font-semibold flex items-center gap-1">
                      {currentFamiliarity === 'seeker' && <Check className="h-3 w-3 text-saffron-gold" />}
                      Seeker
                    </span>
                    <span className="text-[10px] text-muted-foreground">
                      Gentle, foundational clarity
                    </span>
                  </div>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => handleUpdateFamiliarity('practitioner')}>
                  <div className="flex flex-col text-xs">
                    <span className="font-semibold flex items-center gap-1">
                      {currentFamiliarity === 'practitioner' && <Check className="h-3 w-3 text-saffron-gold" />}
                      Practitioner
                    </span>
                    <span className="text-[10px] text-muted-foreground">
                      Balanced contemplative depth
                    </span>
                  </div>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => handleUpdateFamiliarity('advanced')}>
                  <div className="flex flex-col text-xs">
                    <span className="font-semibold flex items-center gap-1">
                      {currentFamiliarity === 'advanced' && <Check className="h-3 w-3 text-saffron-gold" />}
                      Advanced Meditator
                    </span>
                    <span className="text-[10px] text-muted-foreground">
                      Neurobiology & non-dual terms
                    </span>
                  </div>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {/* Quadrant C: Contextual Practice Embodiment */}
        <div className="flex flex-col justify-between rounded-xl border border-border/40 bg-background/40 p-2.5">
          <div>
            <div className="flex items-center justify-between gap-1 mb-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <Wind className="h-3 w-3 text-teal-500" />
                Pattern C · Somatic Embodiment
              </span>
              <span className="text-[9px] font-mono text-teal-500/80 bg-teal-500/10 px-1.5 py-0.5 rounded">
                Pranayama · 3-Min
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground/90 mb-2">
              Ground the teaching directly into your physical breath:
            </p>
          </div>
          <div>
            <button
              type="button"
              onClick={() => openSereneMind('audio', false)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-teal-500/30 bg-teal-500/10 px-3 py-1.5 text-xs font-semibold text-teal-600 dark:text-teal-400 hover:bg-teal-500/20 hover:scale-[1.02] transition-all"
            >
              <span>🫁</span>
              <span>3-Min Serene Mind Reset</span>
            </button>
          </div>
        </div>

        {/* Quadrant D: Surrounding Discourse Window */}
        <div className="flex flex-col justify-between rounded-xl border border-border/40 bg-background/40 p-2.5">
          <div>
            <div className="flex items-center justify-between gap-1 mb-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <BookOpen className="h-3 w-3 text-rose-500" />
                Pattern D · Surrounding Discourse
              </span>
              <span className="text-[9px] font-mono text-rose-500/80 bg-rose-500/10 px-1.5 py-0.5 rounded">
                Context N-1 … N+1
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground/90 mb-2">
              Immersion into the living discourse context:
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {citation && (
              <button
                type="button"
                onClick={handleWatchFullVideo}
                className="inline-flex items-center gap-1.5 rounded-xl border border-red-500/30 bg-red-500/10 px-2.5 py-1 text-xs font-medium text-red-500 hover:bg-red-500/20 transition-all"
              >
                <Video className="h-3 w-3" />
                <span>Watch Full Video</span>
              </button>
            )}
            <button
              type="button"
              onClick={handleOpenDiscourseWindow}
              className="inline-flex items-center gap-1.5 rounded-xl border border-rose-500/30 bg-rose-500/10 px-2.5 py-1 text-xs font-medium text-rose-600 dark:text-rose-400 hover:bg-rose-500/20 transition-all"
            >
              <FileText className="h-3 w-3" />
              <span>Surrounding Discourse Window</span>
            </button>
          </div>
        </div>
      </div>

      {/* Vault Reflection Drawer (Quadrant B) */}
      <AnimatePresence>
        {showVaultReflection && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-3 overflow-hidden rounded-xl border border-emerald-500/30 bg-emerald-500/[0.04] p-3 text-xs"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5">
                <Brain className="h-3.5 w-3.5" />
                Second Brain Vault Resonance
              </span>
              <button
                type="button"
                onClick={() => setShowVaultReflection(false)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>

            {recallingVault ? (
              <p className="text-muted-foreground italic">Recalling related reflections from your vault…</p>
            ) : recalledNotes.length > 0 ? (
              <div className="space-y-1.5">
                <p className="text-muted-foreground">
                  The Guru weaves these insights from your personal spiritual journey:
                </p>
                <ul className="space-y-1 list-disc pl-4 text-foreground/90">
                  {recalledNotes.map((note) => (
                    <li key={note.id}>{note.content}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="text-muted-foreground">
                <p>
                  No existing memories found for this topic yet. As you save notes or reflect with the
                  Guru, your personal Second Brain Vault will connect your insights here.
                </p>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Memgraph Micro-Graph Modal (Quadrant A) */}
      <Dialog open={!!selectedConcept} onOpenChange={(open) => !open && setSelectedConcept(null)}>
        <DialogContent className="max-w-xl rounded-3xl border border-saffron-gold/30 bg-card/95 p-5 shadow-2xl backdrop-blur-2xl">
          <DialogHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-saffron-gold/20 text-saffron-gold text-sm font-bold">
                  ◈
                </span>
                <DialogTitle className="font-serif text-lg font-bold text-foreground">
                  {selectedConcept?.name}
                </DialogTitle>
              </div>
              <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-mono text-amber-500 border border-amber-500/30">
                Memgraph GraphRAG
              </span>
            </div>
            <DialogDescription className="text-xs text-muted-foreground pt-1">
              {selectedConcept?.description}
            </DialogDescription>
          </DialogHeader>

          {/* Interactive @xyflow/react canvas */}
          <div className="mt-2 h-72 w-full rounded-2xl border border-border/40 bg-zinc-950/80 overflow-hidden relative">
            <ReactFlow
              nodes={flowNodes}
              edges={flowEdges}
              nodeTypes={nodeTypes}
              fitView
              fitViewOptions={{ padding: 0.25 }}
              attributionPosition="bottom-right"
              nodesDraggable={true}
              nodesConnectable={false}
              elementsSelectable={true}
              zoomOnScroll={false}
              panOnScroll={false}
              preventScrolling={false}
            >
              <Background color="#f59e0b" gap={16} size={1} />
              <Controls showInteractive={false} className="!bg-background/80 !border-border/40 !rounded-lg" />
            </ReactFlow>
          </div>

          <div className="mt-3 flex items-center justify-between text-xs pt-1 border-t border-border/30">
            <span className="text-muted-foreground text-[11px]">
              Transmitted by <strong>{selectedConcept?.teacher}</strong>
            </span>
            <button
              type="button"
              onClick={() => {
                setSelectedConcept(null);
                navigate('/knowledge-graph');
              }}
              className="inline-flex items-center gap-1 text-saffron-gold hover:underline font-medium"
            >
              <span>Explore Full Knowledge Graph</span>
              <ExternalLink className="h-3 w-3" />
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default DeepenAndTuneBar;
