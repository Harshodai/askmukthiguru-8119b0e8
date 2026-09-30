import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { motion, useReducedMotion } from 'framer-motion';
import { Network, Sparkles, ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

interface GraphNode {
  id: string;
  label: string;
  category: 'core' | 'state' | 'practice' | 'wisdom';
  x: number;
  y: number;
  description: string;
}

const NODE_LAYOUT: Array<{ id: string; key: string; category: GraphNode['category']; x: number; y: number }> = [
  { id: '1', key: 'universalConsciousness', category: 'core', x: 50, y: 35 },
  { id: '2', key: 'beautifulState', category: 'state', x: 28, y: 55 },
  { id: '3', key: 'sufferingState', category: 'state', x: 72, y: 55 },
  { id: '4', key: 'sereneMind', category: 'practice', x: 18, y: 78 },
  { id: '5', key: 'soulSync', category: 'practice', x: 38, y: 82 },
  { id: '6', key: 'fourSacredSecrets', category: 'wisdom', x: 62, y: 82 },
  { id: '7', key: 'sakshi', category: 'wisdom', x: 82, y: 78 },
];

const EDGES: [string, string][] = [
  ['1', '2'],
  ['1', '3'],
  ['2', '4'],
  ['2', '5'],
  ['3', '6'],
  ['3', '7'],
  ['6', '2'],
];

export const WisdomGraphPreview: React.FC = () => {
  const { t } = useTranslation();
  const reduceMotion = useReducedMotion();
  const GRAPH_NODES: GraphNode[] = NODE_LAYOUT.map((n) => ({
    id: n.id,
    category: n.category,
    x: n.x,
    y: n.y,
    label: t(`landing.graph.nodes.${n.key}.label`),
    description: t(`landing.graph.nodes.${n.key}.description`),
  }));
  const [activeNode, setActiveNode] = useState<GraphNode>(GRAPH_NODES[1]);

  return (
    <section className="py-20 px-4 sm:px-6 relative overflow-hidden bg-background">
      <div className="max-w-6xl mx-auto space-y-10">
        <div className="text-center space-y-3 max-w-2xl mx-auto">
          <Badge variant="outline" className="text-amber-800 dark:text-saffron-gold border-saffron-gold/40 px-3 py-1 text-xs">
            <Network className="w-3.5 h-3.5 mr-1.5" /> {t('landing.graph.badge', '8,750+ Node Doctrinal Ontology')}
          </Badge>
          <h2 className="text-3xl sm:text-4xl font-serif font-bold tracking-tight text-foreground">
            {t('landing.graph.heading', 'Explore the Living Knowledge Graph')}
          </h2>
          <p className="text-sm text-muted-foreground leading-relaxed">
            {t('landing.graph.subtitle', 'Every teaching, discourse, and meditation is mapped in a multi-dimensional semantic graph connecting ancient Vedic insights with contemporary neurobiology.')}
          </p>
        </div>

        {/* Double-Bezel Interactive Canvas */}
        <div className="relative rounded-[2.5rem] border border-border/40 bg-zinc-950/80 p-2 sm:p-3 shadow-2xl backdrop-blur-2xl">
          <div className="relative h-[390px] sm:h-[480px] w-full rounded-[2rem] border border-saffron-gold/20 bg-gradient-to-b from-zinc-900/60 via-zinc-950 to-black overflow-hidden flex flex-col justify-between p-4 sm:p-6">
            {/* SVG Connecting Edges */}
            <svg className="absolute inset-0 w-full h-full pointer-events-none">
              {EDGES.map(([srcId, dstId], idx) => {
                const src = GRAPH_NODES.find((n) => n.id === srcId);
                const dst = GRAPH_NODES.find((n) => n.id === dstId);
                if (!src || !dst) return null;
                const isHighlighted = activeNode.id === srcId || activeNode.id === dstId;

                return (
                  <motion.line
                    key={idx}
                    x1={`${src.x}%`}
                    y1={`${src.y}%`}
                    x2={`${dst.x}%`}
                    y2={`${dst.y}%`}
                    stroke={isHighlighted ? 'rgba(234, 179, 8, 0.7)' : 'rgba(255, 255, 255, 0.08)'}
                    strokeWidth={isHighlighted ? 2 : 1}
                    strokeDasharray={isHighlighted ? '5,5' : undefined}
                    initial={reduceMotion ? false : { pathLength: 0, opacity: 0 }}
                    animate={{ pathLength: 1, opacity: isHighlighted ? 0.9 : 0.45 }}
                    transition={{ duration: reduceMotion ? 0 : 0.55, ease: 'easeOut' }}
                  />
                );
              })}
            </svg>

            {/* Interactive Nodes */}
            <div className="absolute inset-0">
              {GRAPH_NODES.map((node) => {
                const isSelected = activeNode.id === node.id;
                return (
                  <div
                    key={node.id}
                    style={{ left: `${node.x}%`, top: `${node.y}%` }}
                    className="absolute -translate-x-1/2 -translate-y-1/2"
                  >
                    <motion.div
                      whileHover={reduceMotion ? undefined : { y: -2 }}
                      whileTap={reduceMotion ? undefined : { scale: 0.97 }}
                      transition={{ duration: 0.16 }}
                    >
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => setActiveNode(node)}
                        aria-pressed={isSelected}
                        aria-label={`${node.label}: ${node.description}`}
                        className={`min-h-11 rounded-xl px-2.5 sm:px-3 transition-[background-color,border-color,box-shadow,color] flex items-center gap-2 ${
                          isSelected
                            ? 'bg-saffron-gold text-zinc-950 font-bold shadow-[0_0_18px_rgba(234,179,8,0.38)] z-20 hover:bg-saffron-gold'
                            : 'bg-zinc-900/95 border border-border/60 text-foreground/80 hover:border-saffron-gold/60 hover:bg-zinc-800 z-10'
                        }`}
                      >
                        <motion.span
                          className="w-2 h-2 shrink-0 rounded-full bg-current"
                          animate={isSelected && !reduceMotion ? { opacity: [0.55, 1, 0.55] } : { opacity: 0.7 }}
                          transition={{ duration: 1.8, repeat: isSelected && !reduceMotion ? Infinity : 0, ease: 'easeInOut' }}
                        />
                        <span className="font-serif text-[10px] sm:text-sm whitespace-nowrap">{node.label}</span>
                      </Button>
                    </motion.div>
                  </div>
                );
              })}
            </div>

            {/* Active Node Detail Card */}
            <motion.div
              key={activeNode.id}
              initial={reduceMotion ? false : { opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="relative z-30 self-start max-w-[min(22rem,calc(100%-1rem))] rounded-xl border border-border/50 bg-zinc-900/95 p-3 sm:p-4 shadow-xl backdrop-blur-md"
              aria-live="polite"
            >
              <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-saffron-gold">
                <Sparkles className="w-3 h-3" /> {t('landing.graph.ontologicalNode', 'Ontological Node')}
              </div>
              <h4 className="font-serif text-base font-bold text-foreground mt-1">{activeNode.label}</h4>
              <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{activeNode.description}</p>
            </motion.div>

            {/* Bottom Explorer Action Link */}
            <div className="relative z-30 self-end">
              <Button asChild variant="outline" className="min-h-11 rounded-full border-saffron-gold/40 bg-saffron-gold/15 px-4 text-xs font-semibold text-saffron-gold hover:bg-saffron-gold/25 hover:text-saffron-gold">
                <Link to="/knowledge-graph">
                  <span>{t('landing.graph.exploreFull', 'Explore Full 3D Graph')}</span>
                  <ArrowUpRight className="w-3.5 h-3.5" />
                </Link>
              </Button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
