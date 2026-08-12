import { Sparkles } from 'lucide-react';

export type GuidanceTone = 'gentle' | 'direct' | 'poetic';
export type FamiliarityLevel = 'beginner' | 'practitioner' | 'advanced';

interface GuidancePreviewProps {
  guruTone: GuidanceTone;
  familiarityLevel: FamiliarityLevel;
}

const toneCopy: Record<GuidanceTone, string> = {
  direct: 'Clear, concise guidance that comes to the practical next step quickly.',
  poetic: 'Reflective language with imagery, while keeping the teaching clear and useful.',
  gentle: 'Warm, steady guidance that makes room for your experience before offering a next step.',
};

const familiarityCopy: Record<FamiliarityLevel, string> = {
  advanced: 'It can use deeper philosophical terms when the teaching supports them.',
  practitioner: 'It balances a teaching with a practical reflection or meditation cue.',
  beginner: 'It explains spiritual terms plainly before building on them.',
};

/** A transparent preview of the response style selected in the seeker profile. */
export function GuidancePreview({ guruTone, familiarityLevel }: GuidancePreviewProps) {
  return (
    <div
      data-testid="guidance-preview"
      aria-live="polite"
      className="rounded-2xl border border-ojas/20 bg-gradient-to-br from-ojas/[0.08] via-card to-card px-4 py-3.5"
    >
      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Sparkles className="h-4 w-4 text-ojas" aria-hidden="true" />
        Your guidance preview
      </div>
      <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
        {toneCopy[guruTone]} {familiarityCopy[familiarityLevel]}
      </p>
      <p className="mt-2 text-xs text-ojas/90">
        Source-aware by design: verified quotations remain attributed; unsupported questions receive a clear limit or clarification.
      </p>
    </div>
  );
}
