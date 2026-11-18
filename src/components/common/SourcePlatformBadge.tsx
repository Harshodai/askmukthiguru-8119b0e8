import React from 'react';
import { Youtube, ExternalLink, BookOpen, Volume2, Globe, Clock, Play } from 'lucide-react';
import { cn } from '@/lib/utils';

export type SourceType = 'youtube' | 'audio' | 'book' | 'web';

export interface SourcePlatformBadgeProps {
  url?: string | null;
  timestampSeconds?: number | null;
  playbackStartSeconds?: number | null;
  channelName?: string | null;
  className?: string;
  showTimestamp?: boolean;
  showDomain?: boolean;
  size?: 'sm' | 'md';
}

const YOUTUBE_HOSTS = new Set([
  'youtube.com',
  'www.youtube.com',
  'youtu.be',
  'music.youtube.com',
  'www.youtu.be',
  'youtube-nocookie.com',
  'www.youtube-nocookie.com',
]);

export const isYouTubeUrl = (url?: string | null): boolean => {
  if (!url) return false;
  try {
    const parsed = new URL(url);
    return YOUTUBE_HOSTS.has(parsed.hostname.toLowerCase());
  } catch {
    return false;
  }
};

export const getCleanDomain = (url?: string | null): string => {
  if (!url) return '';
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url || '';
  }
};

export const formatTimeClock = (sec?: number | null): string => {
  if (sec == null || !Number.isFinite(sec) || sec < 0) return '0:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s < 10 ? '0' : ''}${s}`;
};

export const SourcePlatformBadge: React.FC<SourcePlatformBadgeProps> = ({
  url,
  timestampSeconds,
  playbackStartSeconds,
  channelName,
  className,
  showTimestamp = true,
  showDomain = false,
  size = 'sm',
}) => {
  const isYt = isYouTubeUrl(url);
  const startSec = playbackStartSeconds ?? timestampSeconds;
  const timeLabel = startSec != null ? formatTimeClock(startSec) : null;
  const domain = getCleanDomain(url);

  if (isYt) {
    return (
      <span
        className={cn(
          'inline-flex items-center gap-1.5 rounded-full border border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400 font-medium select-none shadow-2xs transition-colors',
          size === 'sm' ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-xs',
          className
        )}
        title={channelName ? `YouTube · ${channelName}` : 'Recorded Discourse on YouTube'}
      >
        <Youtube className={cn('shrink-0 text-red-600 dark:text-red-400', size === 'sm' ? 'w-3 h-3' : 'w-3.5 h-3.5')} />
        <span className="font-semibold">YouTube</span>
        {showTimestamp && timeLabel && (
          <>
            <span className="opacity-40">·</span>
            <span className="inline-flex items-center gap-0.5 tabular-nums font-mono text-[9px] opacity-90">
              <Clock className="w-2.5 h-2.5 shrink-0" />
              {timeLabel}
            </span>
          </>
        )}
        {showDomain && !timeLabel && <span className="opacity-75">{domain}</span>}
      </span>
    );
  }

  // Audio / Media Clip
  if (url?.startsWith('/api/media/') || url?.endsWith('.mp3') || url?.endsWith('.wav')) {
    return (
      <span
        className={cn(
          'inline-flex items-center gap-1.5 rounded-full border border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300 font-medium select-none shadow-2xs',
          size === 'sm' ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-xs',
          className
        )}
        title="Direct Audio Recording"
      >
        <Volume2 className={cn('shrink-0 text-violet-600 dark:text-violet-400', size === 'sm' ? 'w-3 h-3' : 'w-3.5 h-3.5')} />
        <span className="font-semibold">Audio</span>
        {showTimestamp && timeLabel && (
          <>
            <span className="opacity-40">·</span>
            <span className="tabular-nums font-mono text-[9px] opacity-90">{timeLabel}</span>
          </>
        )}
      </span>
    );
  }

  // General Web or Sacred Literature
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border border-border/60 bg-muted/50 text-muted-foreground font-medium select-none shadow-2xs',
        size === 'sm' ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-xs',
        className
      )}
      title={url ? `Source: ${domain}` : 'Sacred Source Context'}
    >
      <Globe className={cn('shrink-0 text-muted-foreground', size === 'sm' ? 'w-3 h-3' : 'w-3.5 h-3.5')} />
      <span className="truncate max-w-[130px]">{domain || 'Source'}</span>
    </span>
  );
};
