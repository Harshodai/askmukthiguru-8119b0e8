import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Network, Sparkles, ArrowUpRight, Compass, Shield, Heart } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';

interface GraphNode {
  id: string;
  label: string;
  category: 'core' | 'state' | 'practice' | 'wisdom';
  x: number;
  y: number;
  description: string;
}

const GRAPH_NODES: GraphNode[] = [
  { id: '1', label: 'Universal Consciousness', category: 'core', x: 50, y: 35, description: 'The non-dual underlying reality of all existence.' },
  { id: '2', label: 'Beautiful State', category: 'state', x: 28, y: 55, description: 'A neurobiological & spiritual state of peace, connection, and joy.' },
  { id: '3', label: 'Suffering State', category: 'state', x: 72, y: 55, description: 'Self-centric anxiety, fear, and disconnection from life.' },
  { id: '4', label: 'Serene Mind', category: 'practice', x: 18, y: 78, description: 'Pranayama & vagal nerve reset returning mind to stillness.' },
  { id: '5', label: 'Soul Sync', category: 'practice', x: 38, y: 82, description: 'Consciousness alignment meditation to manifest destiny.' },
  { id: '6', label: 'Four Sacred Secrets', category: 'wisdom', x: 62, y: 82, description: 'Wisdom pillars to dissolve conflict and awaken inner power.' },
  { id: '7', label: 'Sakshi (Witness)', category: 'wisdom', x: 82, y: 78, description: 'Pure observing awareness detached from the egoic story.' },
];

const EDGES: [string, string][] = [
  ['1', '2'],
  ['1', '3'],
  ['2', '4'],
  ['2', '5'],
  ['3', '6'],
  ['3', '7'],
  ['4', '2'],
  ['5', '2'],
  ['6', '2'],
];

export const WisdomGraphPreview: React.FC = () => {
  const [activeNode, setActiveNode] = useState<GraphNode>(GRAPH_NODES[1]);

  return (
    <section className="py-20 px-4 sm:px-6 relative overflow-hidden bg-background">
      <div className="max-w-6xl mx-auto space-y-10">
        <div className="text-center space-y-3 max-w-2xl mx-auto">
          <Badge variant="outline" className="text-saffron-gold border-saffron-gold/40 px-3 py-1 text-xs">
            <Network className="w-3.5 h-3.5 mr-1.5" /> 8,750+ Node Doctrinal Ontology
          </Badge>
          <h2 className="text-3xl sm:text-4xl font-serif font-bold tracking-tight text-foreground">
            Explore the Living Knowledge Graph
          </h2>
          <p className="text-sm text-muted-foreground leading-relaxed">
            Every teaching, discourse, and meditation is mapped in a multi-dimensional semantic graph
            connecting ancient Vedic insights with contemporary neurobiology.
          </p>
        </div>

        {/* Double-Bezel Interactive Canvas */}
        <div className="relative rounded-[2.5rem] border border-border/40 bg-zinc-950/80 p-2 sm:p-3 shadow-2xl backdrop-blur-2xl">
          <div className="relative h-[420px] sm:h-[480px] w-full rounded-[2rem] border border-saffron-gold/20 bg-gradient-to-b from-zinc-900/60 via-zinc-950 to-black overflow-hidden flex flex-col justify-between p-6">
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
                    strokeDasharray={isHighlighted ? '4,4' : undefined}
                    animate={isHighlighted ? { strokeDashoffset: [0, -20] } : {}}
                    transition={{ duration: 1.5, repeat: Infinity, ease: 'linear' }}
                  />
                );
              })}
            </svg>

            {/* Interactive Nodes */}
            <div className="absolute inset-0">
              {GRAPH_NODES.map((node) => {
                const isSelected = activeNode.id === node.id;
                return (
                  <motion.button
                    key={node.id}
                    onClick={() => setActiveNode(node)}
                    whileHover={{ scale: 1.15 }}
                    whileTap={{ scale: 0.92 }}
                    style={{ left: `${node.x}%`, top: `${node.y}%` }}
                    className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-2xl p-2.5 sm:p-3 transition-all flex items-center gap-2 ${
                      isSelected
                        ? 'bg-saffron-gold text-zinc-950 font-bold shadow-[0_0_24px_rgba(234,179,8,0.5)] z-20 scale-110'
                        : 'bg-zinc-900/90 border border-border/60 text-foreground/80 hover:border-saffron-gold/60 z-10'
                    }`}
                  >
                    <span className="w-2 h-2 rounded-full bg-current animate-ping" />
                    <span className="font-serif text-xs sm:text-sm whitespace-nowrap">{node.label}</span>
                  </motion.button>
                );
              })}
            </div>

            {/* Active Node Detail Card */}
            <div className="relative z-30 self-start max-w-sm rounded-2xl border border-border/50 bg-zinc-900/90 p-4 shadow-xl backdrop-blur-md">
              <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-saffron-gold">
                <Sparkles className="w-3 h-3" /> Ontological Node
              </div>
              <h4 className="font-serif text-base font-bold text-foreground mt-1">{activeNode.label}</h4>
              <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{activeNode.description}</p>
            </div>

            {/* Bottom Explorer Action Link */}
            <div className="relative z-30 self-end">
              <Link
                to="/knowledge-graph"
                className="inline-flex items-center gap-2 rounded-full bg-saffron-gold/15 border border-saffron-gold/40 px-4 py-2 text-xs font-semibold text-saffron-gold hover:bg-saffron-gold/25 transition-all shadow-sm"
              >
                <span>Explore Full 3D Graph</span>
                <ArrowUpRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
