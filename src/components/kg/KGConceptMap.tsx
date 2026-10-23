import { useTranslation } from 'react-i18next';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { CSSProperties, FormEvent, MouseEvent } from 'react';
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  ArrowRight,
  BookOpen,
  Compass,
  ExternalLink,
  Flame,
  Heart,
  Loader2,
  MessageCircle,
  Search,
  Sparkles,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { getAIConfig } from '@/lib/chat/config';
import { getAccessToken } from '@/lib/chat/auth';

export interface KGNode {
  id: string;
  label: string;
  type: string;
  teacher?: string | null;
  state_category?: string | null;
  content_preview?: string | null;
}

export interface KGEdge {
  source: string;
  target: string;
  label?: string | null;
}

export interface Subgraph {
  nodes: KGNode[];
  edges: KGEdge[];
  query?: string;
  count?: number;
}

export const DEMO_DATA: Subgraph = {
  nodes: [
    { id: '1', label: 'Beautiful State', type: 'State', teacher: 'Sri Preethaji' },
    { id: '2', label: 'Witnessing Awareness', type: 'Practice', teacher: 'Sri Preethaji' },
    { id: '3', label: 'Compassion', type: 'Practice', teacher: 'Sri Preethaji' },
    { id: '4', label: 'Stillness', type: 'Practice', teacher: 'Sri Preethaji' },
    { id: '5', label: 'Sri Krishnaji', type: 'Teacher', teacher: 'Sri Krishnaji' },
    { id: '6', label: 'Observation', type: 'Practice', teacher: 'Sri Krishnaji' },
  ],
  edges: [
    { source: '1', target: '2', label: 'cultivates' },
    { source: '2', target: '3', label: 'inspires' },
    { source: '1', target: '4', label: 'leads to' },
    { source: '5', target: '6', label: 'taught' },
    { source: '6', target: '2', label: 'deepens' },
  ],
};

export interface TypeVisual {
  accent: string;
  soft: string;
  border: string;
  glow: string;
  icon: string;
  badge: string;
}

const TYPE_STYLES: Record<string, TypeVisual> = {
  user: {
    accent: '#f59e0b',
    soft: 'rgba(245,158,11,0.14)',
    border: 'rgba(245,158,11,0.45)',
    glow: '0 0 20px rgba(245,158,11,0.3)',
    icon: '✦',
    badge: 'Seeker (You)',
  },
  inquiry: {
    accent: '#06b6d4',
    soft: 'rgba(6,182,212,0.12)',
    border: 'rgba(6,182,212,0.4)',
    glow: '0 0 16px rgba(6,182,212,0.25)',
    icon: '✧',
    badge: 'Sacred Inquiry',
  },
  beautiful_state: {
    accent: '#10b981',
    soft: 'rgba(16,185,129,0.14)',
    border: 'rgba(16,185,129,0.45)',
    glow: '0 0 20px rgba(16,185,129,0.3)',
    icon: '✺',
    badge: 'Beautiful State',
  },
  suffering_state: {
    accent: '#fb7185',
    soft: 'rgba(251,113,133,0.14)',
    border: 'rgba(251,113,133,0.45)',
    glow: '0 0 18px rgba(251,113,133,0.25)',
    icon: '∆',
    badge: 'Suffering State',
  },
  practice: {
    accent: '#818cf8',
    soft: 'rgba(129,140,248,0.14)',
    border: 'rgba(129,140,248,0.45)',
    glow: '0 0 18px rgba(129,140,248,0.25)',
    icon: '◎',
    badge: 'Sacred Practice',
  },
  teacher: {
    accent: '#f43f5e',
    soft: 'rgba(244,63,94,0.14)',
    border: 'rgba(244,63,94,0.45)',
    glow: '0 0 22px rgba(244,63,94,0.3)',
    icon: '🪷',
    badge: 'Master Teacher',
  },
  concept: {
    accent: '#c084fc',
    soft: 'rgba(192,132,252,0.12)',
    border: 'rgba(192,132,252,0.4)',
    glow: '0 0 16px rgba(192,132,252,0.22)',
    icon: '◈',
    badge: 'Core Teaching',
  },
  memory: {
    accent: '#2dd4bf',
    soft: 'rgba(45,212,191,0.12)',
    border: 'rgba(45,212,191,0.4)',
    glow: '0 0 16px rgba(45,212,191,0.22)',
    icon: '✎',
    badge: 'Inner Reflection',
  },
};

const KNOWN_TEACHERS = new Set(['Sri Preethaji', 'Sri Krishnaji']);
const KNOWN_PRACTICES = new Set([
  'soul sync',
  'serene mind',
  'witnessing awareness',
  'stillness',
  'stillness meditation',
  'compassion',
  'observation',
  'aham',
  'conscious breathing',
]);

const SUFFERING_MARKERS = [
  'suffering',
  'shrink',
  'destruct',
  'inert',
  'anxiet',
  'fear',
  'anger',
  'stress',
  'hurt',
  'guilt',
];

/**
 * Single classifier for suffering states. The badge colour, the chat prompt,
 * and the explanation must never disagree about whether a node is suffering.
 */
function isSufferingState(
  nodeType?: string | null,
  stateCategory?: string | null,
  label?: string | null,
): boolean {
  const type = (nodeType || '').toLowerCase();
  if (type === 'sufferingstate') return true;
  const combined = `${stateCategory || ''} ${label || ''}`.toLowerCase();
  return SUFFERING_MARKERS.some((marker) => combined.includes(marker));
}

export function getNodeVisual(type: string, stateCategory?: string | null, label?: string | null): TypeVisual {
  const t = (type || '').toLowerCase();
  if (t === 'user') return TYPE_STYLES.user;
  if (t === 'practice') return TYPE_STYLES.practice;
  if (t === 'teacher') return TYPE_STYLES.teacher;
  if (t === 'notebookitem' || t === 'inquiry' || t === 'question') return TYPE_STYLES.inquiry;
  if (t === 'memory' || t === 'reflection') return TYPE_STYLES.memory;

  if (t === 'concept') {
    const l = (label || '').toLowerCase();
    if (KNOWN_TEACHERS.has(label || '')) return TYPE_STYLES.teacher;
    if (KNOWN_PRACTICES.has(l) || l.includes('practice') || l.includes('meditation')) return TYPE_STYLES.practice;
    return TYPE_STYLES.concept;
  }

  if (t === 'state' || t === 'beautifulstate' || t === 'sufferingstate') {
    if (isSufferingState(t, stateCategory, label)) return TYPE_STYLES.suffering_state;
    return TYPE_STYLES.beautiful_state;
  }

  return TYPE_STYLES.concept;
}

const SPIRITUAL_EXPLANATIONS: Record<
  string,
  { summary: string; practice?: { name: string; slug: string; duration: string } }
> = {
  'beautiful state': {
    summary:
      'A state of connection, calm, love, and joy free from self-centered suffering. In a beautiful state, heart and mind harmonize with universal intelligence.',
    practice: { name: 'Soul Sync Meditation', slug: 'soul-sync', duration: '15 min' },
  },
  'suffering state': {
    summary:
      'Any state of inner division, resistance, or self-obsession—such as anxiety, fear, hurt, or anger. In Ekam teachings, suffering is a temporary state dissolved by witnessing awareness.',
    practice: { name: 'Serene Mind Practice', slug: 'serene-mind', duration: '3 min' },
  },
  'witnessing awareness': {
    summary:
      'The sacred capacity to observe your inner world—thoughts, emotions, and sensations—without judging, controlling, or escaping them. Observation dissolves inner conflict.',
    practice: { name: 'Witnessing Awareness Reflection', slug: 'wisdom-reflection', duration: '5 min' },
  },
  'soul sync': {
    summary:
      'A foundational meditation combining 8 conscious breath cycles, humming vibration (Bhramari), resting in the silent pause, and meditating on Aham (I Am) to align intention with universal intelligence.',
    practice: { name: 'Soul Sync Guided Meditation', slug: 'soul-sync', duration: '15–20 min' },
  },
  'serene mind': {
    summary:
      'A 3-minute conscious pause that uses 4-in / 6-out rhythmic breathing and steady flame visualization to cool emotional agitation and center the heart.',
    practice: { name: '3-Minute Serene Mind Meditation', slug: 'serene-mind', duration: '3 min' },
  },
  stillness: {
    summary:
      'The quiet space behind thoughts where mental chatter ceases and effortless clarity, peace, and universal connection arise.',
    practice: { name: 'Serene Mind Practice', slug: 'serene-mind', duration: '3 min' },
  },
  'shrinking self': {
    summary:
      'A suffering identity where the self feels small, victimized, inadequate, or withdraws in fear. Observing it without judgment brings liberation.',
    practice: { name: 'Serene Mind Practice', slug: 'serene-mind', duration: '3 min' },
  },
  'destructive self': {
    summary:
      'A suffering identity marked by judgment, blame, aggression, and the need to control. Through witnessing awareness, reactive energy dissolves into peace.',
    practice: { name: 'Soul Sync Meditation', slug: 'soul-sync', duration: '15 min' },
  },
  'inert self': {
    summary:
      'A suffering identity marked by procrastination, emotional numbness, and paralysis. Conscious breathing restores vitality and connection.',
    practice: { name: 'Soul Sync Meditation', slug: 'soul-sync', duration: '15 min' },
  },
  'sri krishnaji': {
    summary:
      'Enlightened philosopher, mystic, and co-creator of Ekam and The Four Sacred Secrets. Sri Krishnaji teaches the science of transforming consciousness from suffering into oneness.',
  },
  'sri preethaji': {
    summary:
      'Spiritual teacher, author, and co-creator of Ekam. Sri Preethaji has guided millions across the world into higher consciousness, beautiful states, and sacred relationships.',
  },
  compassion: {
    summary:
      'The spontaneous arising of love and care when you perceive the interconnectedness of all life. Compassion is the natural expression of a Beautiful State.',
    practice: { name: 'Beautiful State Meditation', slug: 'beautiful-state', duration: '10 min' },
  },
};

function getExplanation(nodeType: string, label: string, stateCategory?: string | null) {
  const norm = (label || '').trim().toLowerCase();
  if (SPIRITUAL_EXPLANATIONS[norm]) return SPIRITUAL_EXPLANATIONS[norm];

  for (const [key, val] of Object.entries(SPIRITUAL_EXPLANATIONS)) {
    if (norm.includes(key)) return val;
  }

  if (isSufferingState(nodeType, stateCategory, label)) {
    return {
      summary:
        'An inner hurdle explored by the seeker. In Ekam teachings, suffering is not your true nature; meeting it with soft observation and conscious breathing allows it to dissolve.',
      practice: { name: 'Serene Mind Practice', slug: 'serene-mind', duration: '3 min' },
    };
  }

  const isBeautiful =
    (stateCategory || '').toLowerCase().includes('beautiful') ||
    ['calm', 'peace', 'joy', 'love', 'connection'].some((w) => norm.includes(w));

  if (isBeautiful) {
    return {
      summary:
        'A luminous state of consciousness marked by connection, calm, and inner peace. Nurturing this state deepens your spiritual foundation.',
      practice: { name: 'Soul Sync Meditation', slug: 'soul-sync', duration: '15 min' },
    };
  }

  return null;
}

function getChatPromptForNode(label: string, nodeType: string, stateCategory?: string | null): string {
  const t = nodeType.toLowerCase();
  const l = label.trim();
  if (t === 'user') {
    return 'How is my spiritual consciousness journey evolving based on our conversations?';
  }
  if (t === 'notebookitem' || t === 'inquiry' || t === 'question') {
    return `I would like to explore this inquiry deeper: "${l}". What more can Sri Krishnaji and Sri Preethaji teach me about this?`;
  }
  if (t === 'practice') {
    return `Can you guide me step-by-step through the ${l} practice and explain how it transforms my inner state?`;
  }
  if (t === 'teacher') {
    return `What are the core teachings of ${l} on awakening and living in a Beautiful State?`;
  }
  if (t === 'state' || t === 'beautifulstate' || t === 'sufferingstate') {
    if (isSufferingState(t, stateCategory, l)) {
      return `I am observing a state of ${l} within myself. How do Ekam teachings guide me to witness and transcend this suffering?`;
    }
    return `How can I sustain and deepen the Beautiful State of ${l} in my everyday life and relationships?`;
  }
  if (t === 'memory' || t === 'reflection') {
    return `Looking back at my reflection on "${l}", what spiritual guidance can help me continue growing?`;
  }
  return `Please share the deeper spiritual wisdom behind ${l} in the Ekam teachings.`;
}

const NODE_WIDTH = 230;
const NODE_HEIGHT = 110;

type WisdomNodeData = {
  label: string;
  nodeType: string;
  teacher?: string | null;
  stateCategory?: string | null;
  contentPreview?: string | null;
  degree: number;
};

type WisdomFlowNode = Node<WisdomNodeData, 'wisdom'>;

const nodeTypes = {
  wisdom: WisdomNode,
};

function WisdomNode({ data, selected }: NodeProps<WisdomFlowNode>) {
  const visual = getNodeVisual(data.nodeType, data.stateCategory, data.label);
  // Bright accents fail WCAG AA as small text on the themed card, so mix toward the foreground (works in light and dark).
  const textAccent = `color-mix(in srgb, ${visual.accent} 50%, hsl(var(--foreground)))`;
  const isUser = data.nodeType.toLowerCase() === 'user';
  const showTeacher = Boolean(data.teacher && KNOWN_TEACHERS.has(data.teacher));

  return (
    <div
      data-testid="kg-node"
      aria-label={data.label}
      className="relative min-w-[180px] max-w-[230px] rounded-2xl border bg-background/95 px-3.5 py-3 shadow-lg backdrop-blur-md transition-all duration-200 hover:-translate-y-0.5 hover:shadow-xl"
      style={{
        borderColor: selected ? visual.accent : visual.border,
        boxShadow: selected ? `${visual.glow}, 0 14px 32px rgba(0,0,0,0.32)` : '0 8px 24px rgba(0,0,0,0.22)',
      }}
    >
      <Handle id="target-top" type="target" position={Position.Top} className="!h-1 !w-8 !border-0 !bg-transparent" />
      <Handle id="target-right" type="target" position={Position.Right} className="!h-8 !w-1 !border-0 !bg-transparent" />
      <Handle id="target-bottom" type="target" position={Position.Bottom} className="!h-1 !w-8 !border-0 !bg-transparent" />
      <Handle id="target-left" type="target" position={Position.Left} className="!h-8 !w-1 !border-0 !bg-transparent" />
      <Handle id="source-top" type="source" position={Position.Top} className="!h-1 !w-8 !border-0 !bg-transparent" />
      <Handle id="source-right" type="source" position={Position.Right} className="!h-8 !w-1 !border-0 !bg-transparent" />
      <Handle id="source-bottom" type="source" position={Position.Bottom} className="!h-1 !w-8 !border-0 !bg-transparent" />
      <Handle id="source-left" type="source" position={Position.Left} className="!h-8 !w-1 !border-0 !bg-transparent" />

      <div className="flex items-start gap-2.5">
        <span
          className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-xl text-sm font-semibold shadow-inner"
          style={{ color: visual.accent, background: visual.soft }}
          aria-hidden="true"
        >
          {visual.icon}
        </span>
        <div className="min-w-0 flex-1">
          <div
            className="text-[9px] font-semibold uppercase tracking-[0.18em]"
            style={{ color: textAccent }}
          >
            {visual.badge}
          </div>
          <div
            className="mt-0.5 line-clamp-2 text-[13px] font-medium leading-snug text-foreground"
            title={data.label}
          >
            {data.label}
          </div>
        </div>
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-1.5 pt-1.5 border-t border-border/30">
        {showTeacher && (
          <span
            className="rounded-full border px-2 py-0.5 text-[9px] font-medium"
            style={{ borderColor: `${visual.accent}55`, color: textAccent }}
          >
            {data.teacher}
          </span>
        )}
        {data.stateCategory && !isUser && (
          <span className="rounded-full border border-border/50 bg-background/50 px-2 py-0.5 text-[9px] text-muted-foreground">
            {data.stateCategory}
          </span>
        )}
        {!isUser && data.degree > 0 && (
          <span className="ms-auto text-[9px] text-muted-foreground">
            {data.degree} {data.degree === 1 ? 'connection' : 'connections'}
          </span>
        )}
      </div>
    </div>
  );
}

function layoutGraph(data: Subgraph): WisdomFlowNode[] {
  const valid = data.nodes.filter((node) => node.id && node.label);
  const user = valid.find((node) => node.type.toLowerCase() === 'user');
  const personal = valid.filter((node) =>
    ['memory', 'notebookitem', 'inquiry', 'question', 'reflection'].includes(node.type.toLowerCase()),
  );
  const statesAndPractices = valid.filter((node) =>
    ['state', 'beautifulstate', 'sufferingstate', 'practice'].includes(node.type.toLowerCase()),
  );
  const conceptsAndTeachers = valid.filter((node) =>
    ['concept', 'teacher', 'doctrine'].includes(node.type.toLowerCase()),
  );

  const degree = new Map<string, number>();
  const adjacency = new Map<string, string[]>();
  for (const node of valid) {
    degree.set(node.id, 0);
    adjacency.set(node.id, []);
  }
  for (const edge of data.edges) {
    if (!degree.has(edge.source) || !degree.has(edge.target)) continue;
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
    adjacency.get(edge.source)?.push(edge.target);
    adjacency.get(edge.target)?.push(edge.source);
  }

  const positions = new Map<string, { x: number; y: number }>();
  const center = { x: 620, y: 380 };
  if (user) positions.set(user.id, { x: center.x - 115, y: center.y - 50 });

  const ringRadius = (count: number, minRadius: number) =>
    count <= 1 ? minRadius : Math.max(minRadius, (count * (NODE_WIDTH + 28)) / (2 * Math.PI));

  const placeRing = (
    items: KGNode[],
    minRadius: number,
    startAngle: number,
    yScale = 0.82,
  ): number => {
    const radius = items.length ? ringRadius(items.length, minRadius) : minRadius;
    items.forEach((node, index) => {
      const angle = startAngle + (index / items.length) * Math.PI * 2;
      positions.set(node.id, {
        x: center.x + Math.cos(angle) * radius - 115,
        y: center.y + Math.sin(angle) * radius * yScale - 50,
      });
    });
    return radius;
  };

  // Concentric Mandala Layout:
  // Center: Student (You)
  // Ring 1: Personal Inquiries, Reflections & Memories (Inner exploration)
  // Ring 2: States & Practices (Transformative bridges)
  // Ring 3: Teachers & Core Wisdom Concepts (Eternal guiding ground)
  const RING_GAP = 120;
  if (personal.length) {
    const personalRadius = placeRing(personal, personal.length <= 2 ? 220 : 260, -Math.PI / 2);
    const statesRadius = placeRing(
      statesAndPractices,
      Math.max(380, personalRadius + RING_GAP),
      -Math.PI / 2 + 0.35,
    );
    placeRing(
      conceptsAndTeachers,
      Math.max(500, statesRadius + RING_GAP),
      -Math.PI / 2 + 0.15,
    );
  } else {
    // When no personal items (e.g. public wisdom search), arrange conceptually
    const statesRadius = placeRing(statesAndPractices, 240, -Math.PI / 2);
    placeRing(conceptsAndTeachers, Math.max(400, statesRadius + RING_GAP), -Math.PI / 2 + 0.25);
  }

  let fallbackIndex = 0;
  return valid.map((node) => {
    let position = positions.get(node.id);
    if (!position) {
      const angle = fallbackIndex * 0.75;
      const radius = 340 + fallbackIndex * 20;
      position = {
        x: center.x + Math.cos(angle) * radius - 115,
        y: center.y + Math.sin(angle) * radius * (260 / 340) - 50,
      };
      fallbackIndex += 1;
    }

    return {
      id: node.id,
      type: 'wisdom',
      position,
      draggable: false,
      selectable: true,
      data: {
        label: node.label,
        nodeType: node.type,
        teacher: node.teacher,
        stateCategory: node.state_category,
        contentPreview: node.content_preview,
        degree: degree.get(node.id) ?? 0,
      },
      style: { width: NODE_WIDTH } satisfies CSSProperties,
    };
  });
}

function directionalHandles(source: { x: number; y: number }, target: { x: number; y: number }) {
  const dx = target.x + NODE_WIDTH / 2 - (source.x + NODE_WIDTH / 2);
  const dy = target.y + NODE_HEIGHT / 2 - (source.y + NODE_HEIGHT / 2);
  const horizontal = Math.abs(dx) >= Math.abs(dy);

  if (horizontal) {
    return {
      sourceHandle: dx >= 0 ? 'source-right' : 'source-left',
      targetHandle: dx >= 0 ? 'target-left' : 'target-right',
    };
  }

  return {
    sourceHandle: dy >= 0 ? 'source-bottom' : 'source-top',
    targetHandle: dy >= 0 ? 'target-top' : 'target-bottom',
  };
}

function edgeStyle(label?: string | null, active = false) {
  const semantic = Boolean(label && !['HAS_MEMORY', 'SAVED_NOTE'].includes(label));
  return {
    stroke: active ? '#f59e0b' : semantic ? '#8a8274' : '#4b463f',
    strokeWidth: active ? 2.4 : semantic ? 1.6 : 1.2,
    opacity: active ? 0.95 : semantic ? 0.75 : 0.45,
  };
}

export const KGConceptMap = ({
  initialQuery = '',
  embedded = false,
}: {
  initialQuery?: string;
  embedded?: boolean;
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [query, setQuery] = useState(initialQuery);
  const [submitted, setSubmitted] = useState(initialQuery);
  const [data, setData] = useState<Subgraph | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDemo, setIsDemo] = useState(false);
  const [isPersonal, setIsPersonal] = useState(false);
  const [needsAuth, setNeedsAuth] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const fetchSubgraph = useCallback(
    async (q: string) => {
      setLoading(true);
      setError(null);
      setNeedsAuth(false);
      setIsDemo(false);
      let personal = false;

      try {
        const { endpoint } = getAIConfig();
        const baseUrl = (endpoint ?? '').replace(/\/api\/chat\/?$/, '');
        const token = await getAccessToken();
        personal = Boolean(token);
        setIsPersonal(personal);

        const effectiveQuery = q.trim();
        const url = personal
          ? `${baseUrl}/api/kg/personal-subgraph?limit=50&query=${encodeURIComponent(effectiveQuery)}`
          : `${baseUrl}/api/kg/subgraph?query=${encodeURIComponent(effectiveQuery || 'beautiful state')}&limit=24`;

        const controller = new AbortController();
        const timeoutId = window.setTimeout(() => controller.abort(), 8000);
        const res = await fetch(url, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          signal: controller.signal,
        });
        window.clearTimeout(timeoutId);

        if (res.status === 401 || res.status === 403) {
          setData(null);
          setSelectedNodeId(null);
          setNeedsAuth(true);
          setError(t('kg.signInRequired', 'Please sign in to view your personal wisdom map.'));
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as Subgraph;

        if (!json.nodes || json.nodes.length === 0) {
          setData(null);
          setSelectedNodeId(null);
          setError(
            personal
              ? t(
                  'kg.noPersonalConcepts',
                  'Your personal wisdom map is empty for now. Save a reflection, memory, or study note to build it.',
                )
              : t('kg.noConceptsFor', 'No teachings found for this search.'),
          );
          return;
        }

        setData(json);
        setSelectedNodeId(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        console.warn('[Wisdom Map] live graph unavailable', message);
        setData(null);
        setSelectedNodeId(null);

        if (personal) {
          setError(
            t('kg.personalMapUnavailable', 'Your personal wisdom map is unavailable right now. Please try again.'),
          );
        } else {
          setData(DEMO_DATA);
          setIsDemo(true);
          setError(null);
        }
      } finally {
        setLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    void fetchSubgraph(submitted);
  }, [submitted, fetchSubgraph]);

  const flowNodes = useMemo(() => (data ? layoutGraph(data) : []), [data]);

  const flowEdges = useMemo<Edge[]>(() => {
    if (!data) return [];
    const selected = selectedNodeId;
    const positions = new Map(flowNodes.map((node) => [node.id, node.position]));

    return data.edges
      .filter((edge) => edge.source && edge.target)
      .map((edge, index) => {
        const sourcePosition = positions.get(edge.source) ?? { x: 0, y: 0 };
        const targetPosition = positions.get(edge.target) ?? { x: 0, y: 0 };
        const handles = directionalHandles(sourcePosition, targetPosition);

        return {
          id: `edge-${index}-${edge.source}-${edge.target}`,
          source: edge.source,
          target: edge.target,
          sourceHandle: handles.sourceHandle,
          targetHandle: handles.targetHandle,
          type: 'smoothstep',
          pathOptions: { borderRadius: 14, offset: 18 },
          label: edge.label && !['HAS_MEMORY', 'SAVED_NOTE'].includes(edge.label) ? edge.label : undefined,
          labelStyle: { fill: '#d6d3d1', fontSize: 9, fontWeight: 600 },
          labelBgStyle: { fill: '#15120e', fillOpacity: 0.92 },
          labelBgPadding: [5, 3] as [number, number],
          style: edgeStyle(edge.label, Boolean(selected && (edge.source === selected || edge.target === selected))),
        };
      });
  }, [data, flowNodes, selectedNodeId]);

  const selectedNode = useMemo(
    () => flowNodes.find((node) => node.id === selectedNodeId) ?? null,
    [flowNodes, selectedNodeId],
  );

  const selectedConnections = useMemo(() => {
    if (!selectedNodeId || !data) return [];
    return data.edges
      .filter((edge) => edge.source === selectedNodeId || edge.target === selectedNodeId)
      .map((edge) => {
        const otherId = edge.source === selectedNodeId ? edge.target : edge.source;
        const other = data.nodes.find((node) => node.id === otherId);
        return {
          id: `${edge.source}-${edge.target}-${edge.label ?? ''}`,
          label: other?.label ?? otherId,
          relation: edge.label ?? 'connected',
        };
      })
      .slice(0, 10);
  }, [data, selectedNodeId]);

  const typeCounts = useMemo(() => {
    if (!data) return [];
    const counts = new Map<string, { badge: string; accent: string; count: number }>();
    for (const node of data.nodes) {
      const visual = getNodeVisual(node.type, node.state_category, node.label);
      const existing = counts.get(visual.badge);
      if (existing) {
        existing.count += 1;
      } else {
        counts.set(visual.badge, { badge: visual.badge, accent: visual.accent, count: 1 });
      }
    }
    return [...counts.values()].sort((a, b) => b.count - a.count);
  }, [data]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSubmitted(query.trim());
  };

  const handleStartInquiryInChat = (promptText: string) => {
    navigate(`/chat?q=${encodeURIComponent(promptText)}`);
  };

  const nodeExplanation = selectedNode
    ? getExplanation(
        selectedNode.data.nodeType,
        selectedNode.data.label,
        selectedNode.data.stateCategory,
      )
    : null;

  const chatPrompt = selectedNode
    ? getChatPromptForNode(
        selectedNode.data.label,
        selectedNode.data.nodeType,
        selectedNode.data.stateCategory,
      )
    : '';

  return (
    <div className={embedded ? 'flex w-full flex-col gap-3' : 'mx-auto flex w-full max-w-6xl flex-col gap-4 p-4 md:p-6'}>
      {/* Header & Metrics */}
      <div className={embedded ? 'sr-only' : 'flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between'}>
        <div>
          <div className="mb-2 flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-ojas/20 bg-ojas/5 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-ojas">
              <Sparkles className="h-3 w-3" />
              {isPersonal ? t('kg.personalBadge', 'Student-Teacher Consciousness Map') : isDemo ? t('kg.showingDemo') : t('kg.title')}
            </span>
            {isPersonal && (
              <span className="text-[11px] text-muted-foreground">
                {t('kg.personalSubtitle', 'Synthesized from your dialogues, reflections, and practices')}
              </span>
            )}
          </div>
          <h2 className="font-sacred text-2xl font-semibold tracking-tight text-foreground md:text-3xl">
            {isPersonal ? t('kg.personalTitle', 'Your Personal Wisdom Map') : t('kg.title')}
          </h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
            {isPersonal
              ? t(
                  'kg.personalDesc',
                  'Just as a master teacher observes the student to guide their inner journey, this sacred map connects your personal inquiries, spiritual states, and memories with the timeless wisdom of Ekam.',
                )
              : t('kg.help')}
          </p>
        </div>

        {data && (
          <div className="grid grid-cols-3 gap-2 md:grid-cols-4">
            <Metric value={data.nodes.length} label={t('kg.relatedConcepts')} />
            <Metric value={data.edges.length} label={t('kg.relationships')} />
            <Metric
              value={data.nodes.filter((node) => ['memory', 'reflection'].includes(node.type.toLowerCase())).length}
              label={t('kg.reflections', 'Reflections')}
            />
            <Metric
              value={
                data.nodes.filter((node) =>
                  ['concept', 'practice', 'state', 'teacher', 'beautifulstate', 'sufferingstate'].includes(
                    node.type.toLowerCase(),
                  ),
                ).length
              }
              label={t('kg.teachings', 'Teachings')}
              hideOnMobile
            />
          </div>
        )}
      </div>

      {/* Search Bar */}
      <form onSubmit={submit} className={embedded ? 'flex gap-2 px-3 pt-3' : 'flex flex-col gap-2 sm:flex-row'}>
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute start-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={
              isPersonal
                ? t('kg.searchPlaceholderPersonal', 'Focus your map: stillness, soul sync, anxiety, witnessing awareness, love…')
                : t('kg.searchPlaceholderGeneral', 'Search a concept, teaching, or practice…')
            }
            aria-label={t('kg.searchAriaLabel', 'Knowledge graph query')}
            className="w-full rounded-2xl border border-border/50 bg-card/60 py-3.5 ps-11 pe-4 text-sm text-foreground shadow-sm outline-none backdrop-blur focus:border-ojas/50 focus:ring-2 focus:ring-ojas/10"
          />
        </div>
        <button
          type="submit"
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl bg-ojas px-4 sm:px-6 py-3 text-sm font-semibold text-primary-foreground shadow-lg shadow-ojas/15 transition hover:shadow-xl disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          {t('kg.explore', 'Explore')}
        </button>
        {submitted && !loading && (
          <button
            type="button"
            onClick={() => {
              setQuery('');
              setSubmitted('');
            }}
            className="inline-flex items-center justify-center gap-2 rounded-2xl border border-border/50 bg-card/60 px-4 py-3.5 text-sm text-muted-foreground hover:bg-card"
          >
            <X className="h-4 w-4" />
            {t('common.clear')}
          </button>
        )}
      </form>

      {/* Error & Auth Notices */}
      {error && !isDemo && (
        <div role="alert" className="rounded-2xl border border-border/50 bg-card/50 px-4 py-3 text-sm text-muted-foreground">
          {error}{' '}
          {needsAuth && (
            <Link to="/auth" className="font-semibold text-ojas underline underline-offset-2 hover:text-ojas/80">
              {t('common.signIn', 'Sign in')}
            </Link>
          )}
        </div>
      )}

      {isDemo && data && (
        <div className="flex flex-wrap items-center justify-center gap-3 rounded-2xl border border-ojas/10 bg-ojas/5 px-4 py-3 text-center text-xs text-muted-foreground">
          <span>{t('kg.showingDemo')}</span>
          <button
            type="button"
            onClick={() => void fetchSubgraph(submitted)}
            className="rounded-lg border border-border/50 bg-background/50 px-3 py-1.5 font-medium text-foreground hover:bg-background"
          >
            {t('common.retry')}
          </button>
        </div>
      )}

      {/* Screen reader live summary */}
      <div className="sr-only" aria-live="polite" role="region" aria-label={t('kg.title', 'Wisdom Map')}>
        <h3>{t('kg.title', 'Wisdom Map')}</h3>
        {loading && <p>{t('kg.loading', 'Loading teachings…')}</p>}
        {data && data.nodes.length > 0 && (
          <p>
            {t('kg.graphSummary', 'Wisdom graph containing {{nodeCount}} concepts and {{edgeCount}} connections.', {
              nodeCount: data.nodes.length,
              edgeCount: data.edges.length,
            })}
          </p>
        )}
      </div>

      {/* Main Flow Canvas & Details Panel */}
      <div className={embedded ? 'grid min-h-[480px]' : 'grid min-h-[540px] gap-4 xl:grid-cols-[minmax(0,1fr)_340px]'}>
        <div
          className={
            embedded
              ? 'relative min-h-[480px] overflow-hidden bg-graph'
              : 'relative min-h-[540px] overflow-hidden rounded-[28px] border border-border/50 bg-graph shadow-2xl'
          }
        >
          {loading ? (
            <div className="flex h-[620px] flex-col items-center justify-center px-6 text-center">
              <div className="relative mb-6 flex h-20 w-20 items-center justify-center">
                <div className="absolute inset-0 rounded-full border border-ojas/20 bg-ojas/5 animate-ping opacity-35" />
                <div className="relative flex h-14 w-14 items-center justify-center rounded-2xl border border-ojas/30 bg-card/80 backdrop-blur-md shadow-xl">
                  <Loader2 className="h-7 w-7 animate-spin text-ojas" />
                </div>
              </div>
              <h3 className="font-sacred text-xl font-medium text-foreground">
                {t('kg.weavingTitle', 'Weaving Your Consciousness Map…')}
              </h3>
              <p className="mt-2 max-w-sm text-xs leading-relaxed text-muted-foreground">
                {t(
                  'kg.weavingDesc',
                  'Connecting your reflections, spiritual inquiries, and meditation practices with the sacred wisdom of Sri Krishnaji and Sri Preethaji.',
                )}
              </p>
            </div>
          ) : data && data.nodes.length ? (
            <>
              {/* Context Pill overlay */}
              <div className="absolute start-4 top-4 z-10 rounded-2xl border border-graph-foreground/10 bg-graph/80 px-3.5 py-2 backdrop-blur-md shadow-sm">
                <div className="text-[9px] font-semibold uppercase tracking-[0.18em] text-ojas">
                  {isPersonal ? t('kg.mandalaTitle', 'Consciousness Mandala') : t('kg.title')}
                </div>
                <div className="mt-0.5 text-xs text-graph-foreground/80">
                  {data.query
                    ? t('kg.focusedOn', 'Focused on: {{query}}', { query: data.query })
                    : t('kg.overlayHint', 'Drag to explore · Click any node for deeper wisdom')}
                </div>
              </div>

              <ReactFlow
                nodes={flowNodes}
                edges={flowEdges}
                nodeTypes={nodeTypes}
                fitView
                fitViewOptions={{ padding: 0.22, maxZoom: 1.15 }}
                minZoom={0.3}
                maxZoom={2}
                nodesDraggable={false}
                nodesConnectable={false}
                elementsSelectable
                panOnDrag
                zoomOnScroll
                onNodeClick={(_event: MouseEvent, node) => setSelectedNodeId(node.id)}
                onPaneClick={() => setSelectedNodeId(null)}
                className="bg-graph"
              >
                <Background gap={28} size={1} color="hsl(var(--border))" />
                <Controls
                  showInteractive={false}
                  className="!m-4 !rounded-xl !border !border-graph-foreground/10 !bg-graph/70 !shadow-lg"
                />
                <MiniMap
                  pannable
                  zoomable
                  nodeStrokeColor={(node) => getNodeVisual(String(node.data?.nodeType ?? ''), String(node.data?.stateCategory ?? ''), String(node.data?.label ?? '')).accent}
                  nodeColor={(node) => getNodeVisual(String(node.data?.nodeType ?? ''), String(node.data?.stateCategory ?? ''), String(node.data?.label ?? '')).soft}
                  nodeBorderRadius={8}
                  maskColor="hsl(var(--graph) / 0.72)"
                  className="!m-4 !overflow-hidden !rounded-xl !border !border-graph-foreground/10 !bg-graph/70"
                />
              </ReactFlow>

              {/* Mobile Drawer on click */}
              {selectedNode && (
                <div
                  className="absolute inset-x-3 bottom-3 z-20 max-h-[80%] overflow-y-auto rounded-3xl border border-white/15 bg-black/90 p-5 text-white shadow-2xl backdrop-blur-xl xl:hidden"
                  role="region"
                  aria-live="polite"
                  aria-label={t('kg.nodeDetails', '{{label}} details', {
                    label: selectedNode.data.label,
                  })}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <span
                        className="inline-block rounded-full px-2.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.14em]"
                        style={{
                          color: getNodeVisual(selectedNode.data.nodeType, selectedNode.data.stateCategory, selectedNode.data.label).accent,
                          background: getNodeVisual(selectedNode.data.nodeType, selectedNode.data.stateCategory, selectedNode.data.label).soft,
                        }}
                      >
                        {getNodeVisual(selectedNode.data.nodeType, selectedNode.data.stateCategory, selectedNode.data.label).badge}
                      </span>
                      <h3 className="mt-1.5 font-sacred text-lg font-semibold text-white">{selectedNode.data.label}</h3>
                      <p className="mt-0.5 text-xs text-white/60">
                        {selectedConnections.length === 1
                          ? t('kg.connectionCountOne', '{{count}} connection', {
                              count: selectedConnections.length,
                            })
                          : t('kg.connectionCountOther', '{{count}} connections', {
                              count: selectedConnections.length,
                            })}
                        {selectedNode.data.teacher ? ` · ${selectedNode.data.teacher}` : ''}
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => setSelectedNodeId(null)}
                      className="min-h-10 min-w-10 shrink-0 text-white/70 hover:bg-white/10 hover:text-white"
                      aria-label={t('kg.closeDetails', 'Close node details')}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>

                  {selectedNode.data.contentPreview && (
                    <div className="mt-3.5 rounded-2xl border border-white/10 bg-white/5 p-3 text-xs leading-relaxed text-white/85">
                      {selectedNode.data.contentPreview}
                    </div>
                  )}

                  <div className="mt-4 flex gap-2">
                    <Button
                      onClick={() => handleStartInquiryInChat(chatPrompt)}
                      className="flex-1 min-h-10 rounded-xl bg-ojas text-xs font-semibold text-primary-foreground shadow-md hover:bg-ojas-dark"
                    >
                      <MessageCircle className="w-3.5 h-3.5 me-1.5" />
                      {t('kg.exploreInChat', 'Explore in Chat')}
                    </Button>
                    {nodeExplanation?.practice && (
                      <Link
                        to={`/practices/${nodeExplanation.practice.slug}`}
                        className="inline-flex min-h-10 items-center justify-center rounded-xl border border-white/20 bg-white/10 px-3 text-xs font-medium text-white hover:bg-white/15"
                      >
                        <Compass className="w-3.5 h-3.5 me-1" />
                        {t('kg.viewGuidedPractice', 'View Guided Practice')}
                      </Link>
                    )}
                  </div>
                </div>
              )}

              {/* Visual Legend Bar at bottom */}
              <div
                className={`absolute inset-x-4 z-10 flex flex-wrap items-center gap-1.5 ${
                  selectedNode ? 'bottom-28 xl:bottom-4' : 'bottom-4'
                }`}
              >
                {typeCounts.map(({ badge, accent, count }) => (
                  <div
                    key={badge}
                    className="flex items-center gap-1.5 rounded-full border border-white/10 bg-black/50 px-2.5 py-1 text-[10px] text-white/80 backdrop-blur-md"
                  >
                    <span className="h-2 w-2 rounded-full" style={{ background: accent }} />
                    <span>{badge}</span>
                    <span className="text-white/40">{count}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            /* Inspiring Empty State */
            <div className="flex h-[620px] flex-col items-center justify-center px-6 py-8 text-center">
              <div className="relative mb-5 flex h-20 w-20 items-center justify-center">
                <div className="absolute inset-0 rounded-full border border-ojas/20 bg-ojas/5 animate-pulse" />
                <div className="relative flex h-14 w-14 items-center justify-center rounded-2xl border border-ojas/30 bg-card/60 backdrop-blur-md shadow-xl">
                  <Sparkles className="h-7 w-7 text-ojas" />
                </div>
              </div>
              <h3 className="font-sacred text-2xl font-medium text-foreground">
                {isPersonal ? t('kg.bloomingTitle', 'Your Personal Wisdom Map is Blooming') : t('kg.title')}
              </h3>
              <p className="mt-2 max-w-md text-xs sm:text-sm leading-relaxed text-muted-foreground">
                {isPersonal
                  ? t(
                      'kg.bloomingDesc',
                      'Begin your dialogue with the Guru or record study reflections to watch your consciousness map unfold with sacred teachings.',
                    )
                  : t('kg.searchToVisualise')}
              </p>

              {isPersonal && (
                <div className="mt-6 w-full max-w-md space-y-2.5 text-start">
                  <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ojas">
                    {t('kg.beginInquiry', 'Begin an Inquiry with the Guru')}
                  </div>
                  <button
                    type="button"
                    onClick={() => handleStartInquiryInChat('How do I shift from a suffering state to a beautiful state?')}
                    className="w-full flex items-center justify-between rounded-xl border border-border/50 bg-card/50 p-3 text-xs text-foreground transition-all hover:bg-card hover:border-ojas/40 group"
                  >
                    <span className="truncate">🌿 How do I shift from a suffering state to a beautiful state?</span>
                    <ArrowRight className="h-3.5 w-3.5 text-muted-foreground group-hover:text-ojas shrink-0 ms-2" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleStartInquiryInChat('Teach me the Serene Mind practice for anxiety & stress')}
                    className="w-full flex items-center justify-between rounded-xl border border-border/50 bg-card/50 p-3 text-xs text-foreground transition-all hover:bg-card hover:border-ojas/40 group"
                  >
                    <span className="truncate">🧘 Teach me the Serene Mind practice for anxiety & stress</span>
                    <ArrowRight className="h-3.5 w-3.5 text-muted-foreground group-hover:text-ojas shrink-0 ms-2" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleStartInquiryInChat('What does Sri Krishnaji teach about Witnessing Awareness?')}
                    className="w-full flex items-center justify-between rounded-xl border border-border/50 bg-card/50 p-3 text-xs text-foreground transition-all hover:bg-card hover:border-ojas/40 group"
                  >
                    <span className="truncate">👁 What does Sri Krishnaji teach about Witnessing Awareness?</span>
                    <ArrowRight className="h-3.5 w-3.5 text-muted-foreground group-hover:text-ojas shrink-0 ms-2" />
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Enhanced Interactive Node Details Sidebar (Desktop) */}
        <aside
          className={
            embedded
              ? 'hidden'
              : 'hidden rounded-[28px] border border-border/50 bg-card/60 p-5 shadow-sm backdrop-blur-md xl:flex xl:flex-col'
          }
        >
          {selectedNode ? (
            <div className="flex h-full flex-col">
              {/* Header */}
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <span
                    className="inline-block rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em]"
                    style={{
                      color: getNodeVisual(selectedNode.data.nodeType, selectedNode.data.stateCategory, selectedNode.data.label).accent,
                      background: getNodeVisual(selectedNode.data.nodeType, selectedNode.data.stateCategory, selectedNode.data.label).soft,
                    }}
                  >
                    {getNodeVisual(selectedNode.data.nodeType, selectedNode.data.stateCategory, selectedNode.data.label).badge}
                  </span>
                  <h3 className="mt-2.5 font-sacred text-xl font-semibold leading-snug text-foreground">
                    {selectedNode.data.label}
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedNodeId(null)}
                  className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                  aria-label={t('kg.closeDetails', 'Close node details')}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              {/* Attributes */}
              {selectedNode.data.teacher && KNOWN_TEACHERS.has(selectedNode.data.teacher) && (
                <DetailRow label={t('kg.masterTeacher', 'Master Teacher')} value={selectedNode.data.teacher} />
              )}
              {selectedNode.data.stateCategory && (
                <DetailRow label={t('kg.consciousnessState', 'Consciousness State')} value={selectedNode.data.stateCategory} />
              )}

              {/* Quote Excerpt or Reflection */}
              {selectedNode.data.contentPreview ? (
                <div className="mt-4 rounded-2xl border border-ojas/20 bg-ojas/5 p-3.5 shadow-sm">
                  <div className="flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-[0.16em] text-ojas">
                    <BookOpen className="h-3 w-3" />
                    {t('kg.reflectionExcerpt', 'Reflection & Dialogue Excerpt')}
                  </div>
                  <p className="mt-2 text-xs leading-relaxed text-foreground/90 whitespace-pre-line italic">
                    "{selectedNode.data.contentPreview}"
                  </p>
                </div>
              ) : nodeExplanation ? (
                <div className="mt-4 rounded-2xl border border-border/40 bg-background/50 p-3.5 shadow-sm">
                  <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                    {t('kg.ekamWisdomEssence', 'Ekam Wisdom Essence')}
                  </div>
                  <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
                    {nodeExplanation.summary}
                  </p>
                </div>
              ) : null}

              {/* Associated Practice Callout */}
              {nodeExplanation?.practice && (
                <div className="mt-4 rounded-2xl border border-prana/30 bg-prana/5 p-3.5">
                  <div className="flex items-center justify-between">
                    <span className="text-[9px] font-semibold uppercase tracking-[0.16em] text-prana">
                      {t('kg.associatedPractice', 'Associated Practice')}
                    </span>
                    <span className="rounded-full bg-prana/10 px-2 py-0.5 text-[9px] font-medium text-prana">
                      {nodeExplanation.practice.duration}
                    </span>
                  </div>
                  <div className="mt-1.5 text-xs font-semibold text-foreground">
                    {nodeExplanation.practice.name}
                  </div>
                  <Link
                    to={`/practices/${nodeExplanation.practice.slug}`}
                    className="mt-2 inline-flex items-center gap-1.5 text-[11px] font-medium text-prana hover:underline"
                  >
                    <span>{t('kg.viewGuidedPractice', 'View Guided Practice')}</span>
                    <ExternalLink className="h-3 w-3" />
                  </Link>
                </div>
              )}

              {/* Connected Nodes List */}
              <div className="mt-4 flex-1 overflow-y-auto">
                <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  {t('kg.relationships')}
                </div>
                {selectedConnections.length ? (
                  <div className="mt-2 divide-y divide-border/30 overflow-hidden rounded-2xl border border-border/40 bg-background/30">
                    {selectedConnections.map((connection) => (
                      <div key={connection.id} className="px-3 py-2.5">
                        <div className="text-xs font-medium text-foreground">{connection.label}</div>
                        <div className="mt-0.5 text-[9px] uppercase tracking-[0.12em] text-muted-foreground">
                          {connection.relation}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-2 text-xs text-muted-foreground">{t('kg.noResults')}</p>
                )}
              </div>

              {/* Chat Exploration CTA */}
              <div className="mt-4 pt-3 border-t border-border/40">
                <Button
                  onClick={() => handleStartInquiryInChat(chatPrompt)}
                  className="w-full min-h-11 rounded-2xl bg-ojas hover:bg-ojas-dark text-primary-foreground shadow-lg shadow-ojas/15 text-xs font-semibold flex items-center justify-center gap-2"
                >
                  <MessageCircle className="h-4 w-4" />
                  <span>{t('kg.continueInChat', 'Continue in Chat')}</span>
                </Button>
              </div>
            </div>
          ) : (
            /* Guide View when no node is selected */
            <div className="flex h-full flex-col justify-between">
              <div>
                <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  {t('kg.guideTitle', 'Sacred Map Guide')}
                </div>
                <div className="mt-4 space-y-4 text-xs leading-relaxed text-foreground/85">
                  <GuideStep
                    number="01"
                    title={t('kg.guideStep1Title', 'Student-Teacher Dynamic')}
                    text={t(
                      'kg.guideStep1Text',
                      'Your node (You) rests at the center. As you chat, the Guru observes your inquiries and spiritual states.',
                    )}
                  />
                  <GuideStep
                    number="02"
                    title={t('kg.guideStep2Title', 'States & Practices')}
                    text={t(
                      'kg.guideStep2Text',
                      'Suffering states (red) show where resistance arises; beautiful states (green) and practices (indigo) reveal your path to freedom.',
                    )}
                  />
                  <GuideStep
                    number="03"
                    title={t('kg.guideStep3Title', 'Deepen Your Inquiry')}
                    text={t(
                      'kg.guideStep3Text',
                      'Click any node to reveal reflections, associated practices, and jump straight into dialogue with the Guru.',
                    )}
                  />
                </div>
              </div>

              <div className="rounded-2xl border border-ojas/15 bg-ojas/5 p-4">
                <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                  <Sparkles className="h-3.5 w-3.5 text-ojas" />
                  <span>{t('kg.consciousnessEvolution', 'Consciousness Evolution')}</span>
                </div>
                <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
                  {t(
                    'kg.quote',
                    '"Wisdom is not merely information; it is the lived transformation from a suffering self into the boundless freedom of connection." — Sri Krishnaji',
                  )}
                </p>
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
};

function Metric({
  value,
  label,
  hideOnMobile = false,
}: {
  value: number;
  label: string;
  hideOnMobile?: boolean;
}) {
  return (
    <div
      className={`rounded-2xl border border-border/50 bg-card/50 px-3 py-2 text-center backdrop-blur-sm ${
        hideOnMobile ? 'hidden md:block' : ''
      }`}
    >
      <div className="text-base font-semibold text-foreground">{value}</div>
      <div className="text-[9px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="mt-3 flex items-center justify-between gap-3 border-b border-border/30 pb-2 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-end font-medium text-foreground">{value}</span>
    </div>
  );
}

function GuideStep({ number, title, text }: { number: string; title: string; text: string }) {
  return (
    <div className="flex gap-3">
      <div className="mt-0.5 text-[10px] font-bold tracking-[0.12em] text-ojas">{number}</div>
      <div>
        <div className="font-medium text-foreground">{title}</div>
        <div className="mt-0.5 text-xs text-muted-foreground">{text}</div>
      </div>
    </div>
  );
}

export default KGConceptMap;
