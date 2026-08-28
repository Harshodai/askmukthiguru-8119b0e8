import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  BookOpen,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Globe,
  Loader2,
  Play,
  Search,
  Sparkles,
  X,
  Youtube,
} from 'lucide-react';
import { Citation } from '@/lib/api';

interface ChunkItem {
  id: string;
  chunk_index: number;
  start_time?: number;
  end_time?: number;
  text: string;
  speaker?: string;
  raptor_level?: number;
}

interface QueryMatch {
  chunk_id: string;
  chunk_index: number;
  start_time?: number;
  match_count: number;
  snippet: string;
}

interface SourceData {
  url: string;
  video_id?: string | null;
  title: string;
  total_chunks: number;
  chunks: ChunkItem[];
  full_text: string;
  matches?: QueryMatch[];
}

interface LinkSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  citation: Citation | null;
  onPlayVideo?: (citation: Citation) => void;
}

function formatSeconds(sec: number): string {
  const mins = Math.floor(sec / 60);
  const remSec = Math.floor(sec % 60);
  return `${mins}:${remSec.toString().padStart(2, '0')}`;
}

export const LinkSearchModal: React.FC<LinkSearchModalProps> = ({
  isOpen,
  onClose,
  citation,
  onPlayVideo,
}) => {
  const [loading, setLoading] = useState(false);
  const [sourceData, setSourceData] = useState<SourceData | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeTab, setActiveTab] = useState<'reader' | 'websearch'>('reader');
  const [currentMatchIndex, setCurrentMatchIndex] = useState(0);
  
  // Web search related state
  const [webQuery, setWebQuery] = useState('');
  const [webResults, setWebResults] = useState<Array<{ title: string; text: string; source_url: string }>>([]);
  const [webSearching, setWebSearching] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);

  // Fetch source details when citation changes
  useEffect(() => {
    if (!isOpen || !citation?.url) return;

    let isMounted = true;
    setLoading(true);
    setSearchTerm('');
    setCurrentMatchIndex(0);

    const fetchSource = async () => {
      try {
        const res = await fetch(
          `/api/search/inspect-source?url=${encodeURIComponent(citation.url)}`
        );
        if (res.ok) {
          const data = await res.json();
          if (isMounted) {
            setSourceData(data);
          }
        }
      } catch (err) {
        console.error('Failed to inspect source', err);
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchSource();

    return () => {
      isMounted = false;
    };
  }, [isOpen, citation]);

  // Execute web discourse search
  const handleWebSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!webQuery.trim()) return;
    setWebSearching(true);
    try {
      const res = await fetch('/api/search/web-discourse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: webQuery.trim(), max_results: 5 }),
      });
      if (res.ok) {
        const data = await res.json();
        setWebResults(data.results || []);
      }
    } catch (err) {
      console.error('Web search error', err);
    } finally {
      setWebSearching(false);
    }
  };

  if (!isOpen || !citation) return null;

  const isYouTube = citation.url.includes('youtube.com') || citation.url.includes('youtu.be');

  // Compute text chunks with highlighted keywords
  const chunksToDisplay = sourceData?.chunks || [];
  const filteredChunks = searchTerm.trim()
    ? chunksToDisplay.filter((c) =>
        c.text.toLowerCase().includes(searchTerm.trim().toLowerCase())
      )
    : chunksToDisplay;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-black/80 backdrop-blur-md">
        {/* Backdrop click */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="absolute inset-0"
        />

        {/* Modal Window */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 15 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 15 }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
          className="relative w-full max-w-4xl max-h-[90vh] flex flex-col rounded-3xl border border-saffron-gold/30 bg-zinc-950/95 shadow-2xl overflow-hidden ring-1 ring-white/10 text-white z-10"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-white/10 bg-zinc-900/60 backdrop-blur-md">
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <div className="w-10 h-10 rounded-2xl bg-saffron-gold/15 flex items-center justify-center shrink-0 border border-saffron-gold/30">
                {isYouTube ? (
                  <Youtube className="w-5 h-5 text-red-400" />
                ) : (
                  <BookOpen className="w-5 h-5 text-saffron-gold" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <span className="font-mono text-[10px] uppercase tracking-wider text-saffron-gold">
                  In-Situ Source & Wisdom Inspector
                </span>
                <h3 className="font-serif text-base font-bold text-white truncate">
                  {sourceData?.title || citation.title || 'Spiritual Discourse Source'}
                </h3>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              {isYouTube && onPlayVideo && (
                <button
                  type="button"
                  onClick={() => {
                    onClose();
                    onPlayVideo(citation);
                  }}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-red-600/20 hover:bg-red-600/30 text-red-400 text-xs font-semibold border border-red-500/30 transition-all"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span className="hidden sm:inline">Play Video</span>
                </button>
              )}
              <a
                href={citation.url}
                target="_blank"
                rel="noopener noreferrer"
                className="p-2 rounded-full hover:bg-white/10 text-white/60 hover:text-white transition-colors"
                title="Open original link"
              >
                <ExternalLink className="w-4 h-4" />
              </a>
              <button
                type="button"
                onClick={onClose}
                className="p-2 rounded-full hover:bg-white/10 text-white/60 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Sub-Header Tabs & Search Controls */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 px-5 py-3 border-b border-white/10 bg-zinc-900/30">
            {/* Tabs */}
            <div className="flex items-center gap-1 bg-black/40 p-1 rounded-xl border border-white/10 self-start">
              <button
                type="button"
                onClick={() => setActiveTab('reader')}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  activeTab === 'reader'
                    ? 'bg-saffron-gold text-zinc-950 font-bold shadow-md'
                    : 'text-white/60 hover:text-white'
                }`}
              >
                <BookOpen className="w-3.5 h-3.5 inline mr-1.5" />
                Discourse Transcript ({sourceData?.total_chunks || 0} chunks)
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('websearch')}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  activeTab === 'websearch'
                    ? 'bg-saffron-gold text-zinc-950 font-bold shadow-md'
                    : 'text-white/60 hover:text-white'
                }`}
              >
                <Globe className="w-3.5 h-3.5 inline mr-1.5" />
                Search Related Teachings
              </button>
            </div>

            {/* In-Document Search Input (when on reader tab) */}
            {activeTab === 'reader' && (
              <div className="relative flex-1 sm:max-w-xs">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-white/40" />
                <input
                  type="text"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  placeholder="Search within this transcript..."
                  className="w-full bg-black/50 border border-white/10 rounded-xl pl-9 pr-8 py-1.5 text-xs text-white placeholder-white/40 focus:outline-none focus:border-saffron-gold/50 transition-colors"
                />
                {searchTerm && (
                  <button
                    type="button"
                    onClick={() => setSearchTerm('')}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-white/40 hover:text-white"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Body Content */}
          <div ref={containerRef} className="flex-1 overflow-y-auto p-5 space-y-4 custom-scrollbar">
            {loading ? (
              <div className="flex flex-col items-center justify-center py-16 text-white/60">
                <Loader2 className="w-8 h-8 animate-spin text-saffron-gold mb-3" />
                <p className="text-sm font-sans">Retrieving verified transcript & index points...</p>
              </div>
            ) : activeTab === 'reader' ? (
              /* Reader View */
              filteredChunks.length === 0 ? (
                <div className="text-center py-12 text-white/50">
                  <p className="text-sm">No passages found matching "{searchTerm}".</p>
                  <button
                    type="button"
                    onClick={() => setSearchTerm('')}
                    className="mt-2 text-xs text-saffron-gold hover:underline"
                  >
                    Clear search filter
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  {searchTerm && (
                    <div className="p-2.5 rounded-xl bg-saffron-gold/10 border border-saffron-gold/20 text-xs text-saffron-gold flex items-center justify-between">
                      <span>
                        Found {filteredChunks.length} matching passage{filteredChunks.length === 1 ? '' : 's'}
                      </span>
                    </div>
                  )}

                  {filteredChunks.map((chunk) => {
                    const startSec = chunk.start_time || 0;
                    return (
                      <div
                        key={chunk.id}
                        className="p-4 rounded-2xl bg-white/[0.03] border border-white/5 hover:border-saffron-gold/30 transition-all text-left"
                      >
                        <div className="flex items-center justify-between gap-2 mb-2 pb-1.5 border-b border-white/5 text-[11px] text-white/40">
                          <span className="font-mono text-saffron-gold font-medium">
                            {chunk.speaker || 'Sri Krishnaji / Sri Preethaji'}
                          </span>
                          {startSec > 0 && (
                            <span className="font-mono bg-white/5 px-2 py-0.5 rounded-md">
                              {formatSeconds(startSec)}
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-white/90 leading-relaxed font-sans font-normal">
                          {searchTerm.trim() ? (
                            <HighlightedText text={chunk.text} highlight={searchTerm.trim()} />
                          ) : (
                            chunk.text
                          )}
                        </p>
                      </div>
                    );
                  })}
                </div>
              )
            ) : (
              /* Scoped Web Search Tab */
              <div className="space-y-4">
                <form onSubmit={handleWebSearch} className="flex gap-2">
                  <div className="relative flex-1">
                    <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
                    <input
                      type="text"
                      value={webQuery}
                      onChange={(e) => setWebQuery(e.target.value)}
                      placeholder="Search related teachings across Ekam & spiritual archives..."
                      className="w-full bg-black/60 border border-white/15 rounded-2xl pl-10 pr-4 py-2.5 text-xs text-white placeholder-white/40 focus:outline-none focus:border-saffron-gold transition-all shadow-inner"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={webSearching || !webQuery.trim()}
                    className="px-4 py-2.5 rounded-2xl bg-saffron-gold text-zinc-950 font-bold text-xs hover:bg-amber-400 disabled:opacity-50 transition-all flex items-center gap-1.5 shrink-0 shadow-md"
                  >
                    {webSearching ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <>
                        <Sparkles className="w-3.5 h-3.5" />
                        <span>Search</span>
                      </>
                    )}
                  </button>
                </form>

                {webResults.length > 0 && (
                  <div className="space-y-3 mt-4">
                    {webResults.map((r, idx) => (
                      <div
                        key={idx}
                        className="p-4 rounded-2xl bg-white/[0.03] border border-white/10 hover:border-saffron-gold/30 transition-all text-left"
                      >
                        <h4 className="font-serif text-sm font-semibold text-saffron-gold mb-1">
                          {r.title}
                        </h4>
                        <p className="text-xs text-white/80 leading-relaxed mb-2">
                          {r.text}
                        </p>
                        <a
                          href={r.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-[11px] text-white/50 hover:text-saffron-gold transition-colors font-mono"
                        >
                          <ExternalLink className="w-3 h-3" />
                          <span className="truncate max-w-sm">{r.source_url}</span>
                        </a>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};

// Helper component to highlight search terms inside text
const HighlightedText: React.FC<{ text: string; highlight: string }> = ({ text, highlight }) => {
  if (!highlight.trim()) return <>{text}</>;
  const regex = new RegExp(`(${highlight.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
  const parts = text.split(regex);

  return (
    <>
      {parts.map((part, i) =>
        regex.test(part) ? (
          <mark key={i} className="bg-amber-400 text-zinc-950 px-1 py-0.5 rounded font-medium">
            {part}
          </mark>
        ) : (
          part
        )
      )}
    </>
  );
};
