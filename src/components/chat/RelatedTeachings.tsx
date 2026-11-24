import React from 'react';
import { useTranslation } from 'react-i18next';
import type { Citation } from '@/lib/chat/types';
import { resolveAttributionLabel } from '@/lib/chat/types';
import type { DiscourseCitation } from './CitationCard';
import DiscourseAudioStrip from './DiscourseAudioStrip';

interface RelatedTeachingsProps {
  clips?: Citation[];
  onOpenVideoModal?: (citation: DiscourseCitation) => void;
}

/** Abstain-only list: verbatim clips that relate to the question but do not answer it.
 *  Never citations; quote text is rendered exactly as stored. */
export const RelatedTeachings: React.FC<RelatedTeachingsProps> = ({ clips, onOpenVideoModal }) => {
  const { t } = useTranslation();
  if (!clips || clips.length === 0) return null;
  return (
    <section data-testid="related-teachings" className="mt-3.5 space-y-3">
      <h4 className="text-[13px] font-medium text-muted-foreground">
        {t('chat.relatedTeachings.heading', 'Related teachings, not a direct answer')}
      </h4>
      {clips.map((clip, i) => (
        <div key={clip.url + i} className="space-y-1.5 rounded-lg border border-border/50 p-3">
          <p className="text-[12px] text-muted-foreground">{resolveAttributionLabel(clip)}</p>
          <blockquote className="whitespace-pre-wrap text-[14px] leading-relaxed">
            {clip.quote ?? clip.textSnippet}
          </blockquote>
          <DiscourseAudioStrip citation={clip} onOpenVideoModal={onOpenVideoModal} />
        </div>
      ))}
    </section>
  );
};

export default RelatedTeachings;
