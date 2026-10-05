import React, { useState, useMemo, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import { Play, Pause, Sparkles, Youtube, ExternalLink, Maximize2, Volume2 } from 'lucide-react';
import type { Citation } from '@/lib/chat/types';
import type { DiscourseCitation } from './CitationCard';
import { resolveAttributionLabel } from '@/lib/chat/types';

interface DiscourseAudioStripProps {
  citation?: Citation | DiscourseCitation | null;
  teacher?: string;
  title?: string;
  url?: string;
  playbackStartSeconds?: number;
  playbackEndSeconds?: number;
  onOpenVideoModal?: (citation: DiscourseCitation) => void;
  className?: string;
}

/** Extract YouTube 11-char video ID */
const extractYouTubeId = (rawUrl?: string | null): string | null => {
  if (!rawUrl) return null;
  try {
    const parsed = new URL(rawUrl);
    const hostname = parsed.hostname.toLowerCase().replace(/^www\./, '');
    let candidate: string | null = null;
    if (hostname === 'youtu.be') {
      candidate = parsed.pathname.split('/').filter(Boolean)[0] ?? null;
    } else if (hostname === 'youtube.com') {
      if (parsed.pathname === '/watch') candidate = parsed.searchParams.get('v');
      if (parsed.pathname.startsWith('/embed/')) candidate = parsed.pathname.split('/')[2] ?? null;
      if (parsed.pathname.startsWith('/shorts/')) candidate = parsed.pathname.split('/')[2] ?? null;
    }
    return candidate && /^[A-Za-z0-9_-]{11}$/.test(candidate) ? candidate : null;
  } catch {
    return null;
  }
};

const formatSeconds = (sec?: number | null): string => {
  if (sec == null || !Number.isFinite(sec)) return '00:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
};

export const DiscourseAudioStrip: React.FC<DiscourseAudioStripProps> = ({
  citation,
  teacher,
  title,
  url,
  playbackStartSeconds,
  playbackEndSeconds,
  onOpenVideoModal,
  className = '',
}) => {
  const { t } = useTranslation();
  const [isPlaying, setIsPlaying] = useState(false);
  const [showVideoEmbed, setShowVideoEmbed] = useState(false);
  const [embedError, setEmbedError] = useState(false);

  const effectiveUrl = citation?.url || url || '';
  const videoId = useMemo(() => extractYouTubeId(effectiveUrl), [effectiveUrl]);

  const effectiveSpeaker = useMemo(() => {
    if (teacher) return teacher;
    if (citation) {
      const resolved = resolveAttributionLabel(citation as Citation);
      if (resolved) return resolved;
    }
    return 'Source recording';
  }, [teacher, citation]);

  const effectiveTitle = useMemo(() => {
    if (title) return title;
    if (citation && 'title' in citation && citation.title) return citation.title;
    if (citation && 'source' in citation && citation.source) return citation.source;
    return 'Authentic Discourse Teaching';
  }, [title, citation]);

  const startSec = useMemo(() => {
    if (playbackStartSeconds != null) return playbackStartSeconds;
    if (citation && 'playbackStartSeconds' in citation && citation.playbackStartSeconds != null) {
      return citation.playbackStartSeconds;
    }
    if (citation && 'startTimestamp' in citation && citation.startTimestamp != null) {
      return citation.startTimestamp;
    }
    if (citation && 'timestampSeconds' in citation && citation.timestampSeconds != null) {
      return citation.timestampSeconds;
    }
    return 0;
  }, [playbackStartSeconds, citation]);

  const endSec = useMemo(() => {
    if (playbackEndSeconds != null) return playbackEndSeconds;
    if (citation && 'playbackEndSeconds' in citation && citation.playbackEndSeconds != null) {
      return citation.playbackEndSeconds;
    }
    if (citation && 'endTimestamp' in citation && citation.endTimestamp != null) {
      return citation.endTimestamp;
    }
    return null;
  }, [playbackEndSeconds, citation]);

  // Compute duration label, e.g. "(01:16 – 02:45)"
  const durationLabel = useMemo(() => {
    if (startSec > 0 && endSec != null && endSec > startSec) {
      return `${formatSeconds(startSec)} – ${formatSeconds(endSec)}`;
    }
    if (startSec > 0) {
      return formatSeconds(startSec);
    }
    if (endSec != null && endSec > 0) {
      return `00:00 – ${formatSeconds(endSec)}`;
    }
    return '01:16 – 02:45';
  }, [startSec, endSec]);

  // Safe integer bounds for YouTube iframe embed
  const iframeStart = Math.max(0, Math.ceil(startSec));
  const iframeEnd = endSec != null && Math.floor(endSec) > iframeStart ? Math.floor(endSec) : undefined;
  const endParam = iframeEnd != null ? `&end=${iframeEnd}` : '';

  const handleTogglePlay = () => {
    if (!videoId) {
      // If no video ID, open citation URL in new tab
      if (effectiveUrl) window.open(effectiveUrl, '_blank', 'noopener,noreferrer');
      return;
    }
    setIsPlaying((prev) => !prev);
  };

  const handleOpenModal = () => {
    if (!onOpenVideoModal) return;
    const discourseCitation: DiscourseCitation = {
      index: 1,
      url: effectiveUrl,
      title: effectiveTitle,
      speaker: effectiveSpeaker,
      startTimestamp: startSec,
      playbackStartSeconds: startSec,
      playbackEndSeconds: endSec ?? undefined,
    };
    onOpenVideoModal(discourseCitation);
  };

  const teacherInitials = useMemo(() => {
    if (effectiveSpeaker.includes('Preethaji')) return 'SP';
    if (effectiveSpeaker.includes('Krishnaji')) return 'SK';
    return 'EG';
  }, [effectiveSpeaker]);

  return (
    <div
      data-testid="discourse-audio-strip"
      className={`my-3 overflow-hidden rounded-2xl border border-saffron-gold/30 bg-gradient-to-r from-saffron-gold/15 via-card/95 to-card/90 p-3 shadow-sm backdrop-blur-md transition-all duration-200 hover:border-saffron-gold/50 ${className}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Left: Teacher Avatar & Discourse Metadata */}
        <div className="flex items-center gap-3 min-w-0 flex-1">
          {/* Sacred Avatar Ring */}
          <div className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-saffron-gold to-amber-600 text-white shadow-sm ring-2 ring-saffron-gold/40">
            <span className="font-serif text-xs font-bold tracking-tight">{teacherInitials}</span>
            <span className="absolute -bottom-0.5 -right-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-background ring-1 ring-saffron-gold/50">
              <Sparkles className="h-2 w-2 text-saffron-gold" aria-hidden="true" />
            </span>
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span className="font-serif text-xs font-semibold text-foreground truncate">
                {effectiveSpeaker}
              </span>
              <span className="rounded-full bg-saffron-gold/20 px-1.5 py-0.2 text-[9px] font-medium text-saffron-gold uppercase tracking-wider">
                Source clip
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground truncate" title={effectiveTitle}>
              {effectiveTitle}
            </p>
          </div>
        </div>

        {/* Right: Live Playback Button & Sacred Waveform */}
        <div className="flex items-center gap-2.5 shrink-0">
          {/* Sacred Waveform Visualizer */}
          <div
            className="hidden sm:flex items-center gap-0.5 px-1 py-1"
            aria-hidden="true"
            title={isPlaying ? 'Source recording playing' : 'Sacred acoustic cadence'}
          >
            {[10, 18, 8, 16, 22, 14, 20, 11, 19, 12].map((height, idx) => (
              <motion.span
                key={idx}
                animate={isPlaying ? { height: [height * 0.35, height, height * 0.25] } : { height: 4 }}
                transition={
                  isPlaying
                    ? { duration: 0.65, repeat: Infinity, delay: idx * 0.05, ease: 'easeInOut' }
                    : { duration: 0.2 }
                }
                className="w-1 rounded-full bg-saffron-gold/80"
                style={{ minHeight: '4px' }}
              />
            ))}
          </div>

          {/* Primary Action Button: [▶️ Play source clip (01:16 – 02:45)] */}
          <button
            type="button"
            data-testid="discourse-audio-play-button"
            onClick={handleTogglePlay}
            className={`inline-flex items-center gap-2 rounded-xl px-3 py-1.5 text-xs font-semibold shadow-sm transition-all duration-200 ${
              isPlaying
                ? 'bg-amber-600 text-white hover:bg-amber-700 ring-2 ring-saffron-gold/40'
                : 'bg-saffron-gold text-primary-foreground hover:bg-amber-500 hover:scale-[1.02]'
            }`}
            aria-label={isPlaying ? 'Pause source clip' : `Play source clip (${durationLabel})`}
          >
            {isPlaying ? (
              <Pause className="h-3.5 w-3.5 fill-current" />
            ) : (
              <Play className="h-3.5 w-3.5 fill-current ml-0.5" />
            )}
            <span className="whitespace-nowrap">
              {isPlaying ? 'Pause' : 'Play source clip'}{' '}
              <span className="font-mono text-[11px] opacity-90">({durationLabel})</span>
            </span>
          </button>

          {/* Expand Video Preview Toggle / Modal Link */}
          {videoId && (
            <button
              type="button"
              onClick={() => {
                if (onOpenVideoModal) {
                  handleOpenModal();
                } else {
                  setShowVideoEmbed((v) => !v);
                }
              }}
              title="Watch discourse video"
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-saffron-gold/30 bg-background/50 text-saffron-gold hover:bg-saffron-gold/15 transition-colors"
            >
              <Youtube className="h-3.5 w-3.5" />
            </button>
          )}

          {effectiveUrl && (
            <a
              href={effectiveUrl}
              target="_blank"
              rel="noopener noreferrer"
              title="Open source video on YouTube"
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-border/40 bg-background/40 text-muted-foreground hover:text-foreground hover:bg-background/80 transition-colors"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </div>
      </div>

      {/* Embedded YouTube Playback Canvas when Playing or Previewing */}
      <AnimatePresence>
        {(isPlaying || showVideoEmbed) && videoId && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="mt-3 overflow-hidden rounded-xl border border-saffron-gold/30 bg-black/95 shadow-inner"
          >
            <div className="relative aspect-video max-h-[240px] w-full">
              <iframe
                className="h-full w-full"
                src={`https://www.youtube.com/embed/${videoId}?autoplay=1&start=${iframeStart}${endParam}&enablejsapi=1&origin=${encodeURIComponent(
                  typeof window !== 'undefined' ? window.location.origin : ''
                )}`}
                title={effectiveTitle}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            </div>
            <div className="flex items-center justify-between px-3 py-1.5 bg-zinc-950 text-[11px] text-zinc-400 border-t border-zinc-800">
              <div className="flex items-center gap-1.5">
                <Volume2 className="h-3 w-3 text-saffron-gold animate-pulse" />
                <span>
                  Playing {effectiveSpeaker} ({durationLabel})
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setIsPlaying(false)}
                  className="hover:text-white transition-colors"
                >
                  Stop Audio
                </button>
                {onOpenVideoModal && (
                  <button
                    type="button"
                    onClick={handleOpenModal}
                    className="text-saffron-gold hover:underline"
                  >
                    Fullscreen Modal ↗
                  </button>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default DiscourseAudioStrip;
