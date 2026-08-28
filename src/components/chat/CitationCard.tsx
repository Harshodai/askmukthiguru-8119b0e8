import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Youtube, Play, Clock, Quote, Sparkles, ExternalLink, X } from 'lucide-react';
import { Dialog, DialogContent } from '@/components/ui/dialog';

export interface DiscourseCitation {
  index: number;
  url: string;
  title?: string;
  speaker?: 'Sri Preethaji' | 'Sri Krishnaji' | 'Ekams Wisdom';
  startTimestamp?: number; // in seconds
  endTimestamp?: number;
  quote?: string;
  channelName?: string;
}

interface CitationBadgeProps {
  citation: DiscourseCitation;
  onOpenVideoModal: (citation: DiscourseCitation) => void;
}

export const CitationBadge: React.FC<CitationBadgeProps> = ({ citation, onOpenVideoModal }) => {
  const [hovered, setHovered] = useState(false);

  const formatTimestamp = (sec?: number) => {
    if (!sec) return '00:00';
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  return (
    <span className="relative inline-block align-super" onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}>
      <button
        type="button"
        onClick={() => onOpenVideoModal(citation)}
        className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-md border border-saffron-gold/40 bg-saffron-gold/10 px-1 font-mono text-[10px] font-semibold text-saffron-gold transition-all hover:scale-110 hover:bg-saffron-gold/20 focus:outline-none"
      >
        {citation.index}
      </button>

      {/* Hovercard Preview */}
      <AnimatePresence>
        {hovered && (
          <motion.div
            initial={{ opacity: 0, y: 6, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 4, scale: 0.96 }}
            transition={{ duration: 0.18 }}
            className="absolute bottom-full left-1/2 z-50 mb-2 w-72 -translate-x-1/2 rounded-2xl border border-border/50 bg-card/95 p-3 shadow-xl backdrop-blur-xl"
          >
            <div className="flex items-start gap-2.5">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-red-500/10 text-red-500">
                <Youtube className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="line-clamp-1 font-serif text-xs font-semibold text-foreground">
                  {citation.title || 'Sacred Discourse Teaching'}
                </p>
                <div className="mt-0.5 flex items-center gap-2 text-[10px] text-muted-foreground">
                  <span className="text-saffron-gold">{citation.speaker || 'Ekams Teaching'}</span>
                  {citation.startTimestamp && (
                    <span className="flex items-center gap-0.5">
                      <Clock className="h-2.5 w-2.5" /> {formatTimestamp(citation.startTimestamp)}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {citation.quote && (
              <p className="mt-2 line-clamp-2 border-l-2 border-saffron-gold/30 pl-2 font-serif text-[11px] italic text-muted-foreground">
                "{citation.quote}"
              </p>
            )}

            <button
              type="button"
              onClick={() => onOpenVideoModal(citation)}
              className="mt-2.5 flex w-full items-center justify-center gap-1.5 rounded-xl bg-saffron-gold/15 py-1.5 text-xs font-medium text-saffron-gold hover:bg-saffron-gold/25 transition-colors"
            >
              <Play className="h-3 w-3 fill-current" /> Watch Discourse Segment
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </span>
  );
};

export const DiscourseVideoModal: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  citation: DiscourseCitation | null;
}> = ({ isOpen, onClose, citation }) => {
  if (!citation) return null;

  // Extract video ID and start time
  let videoId = '';
  try {
    const urlObj = new URL(citation.url);
    videoId = urlObj.searchParams.get('v') || urlObj.pathname.replace('/', '');
  } catch {
    videoId = citation.url;
  }
  const start = citation.startTimestamp || 0;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl overflow-hidden rounded-3xl border-border/50 bg-card/95 p-0 shadow-2xl backdrop-blur-2xl">
        <div className="relative aspect-video w-full bg-black">
          <iframe
            className="h-full w-full"
            src={`https://www.youtube.com/embed/${videoId}?autoplay=1&start=${start}&enablejsapi=1`}
            title={citation.title || 'Discourse Video'}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        </div>
        <div className="p-4 sm:p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="font-serif text-base font-semibold text-foreground">
                {citation.title || 'Sacred Discourse'}
              </h3>
              <p className="text-xs text-saffron-gold">{citation.speaker || 'Ekams Wisdom'}</p>
            </div>
            <a
              href={citation.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              Open YouTube <ExternalLink className="h-3 w-3" />
            </a>
          </div>
          {citation.quote && (
            <div className="mt-3 rounded-xl border border-saffron-gold/20 bg-saffron-gold/5 p-3 text-xs italic text-muted-foreground">
              "{citation.quote}"
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};
