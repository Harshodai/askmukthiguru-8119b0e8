import { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  submitFacultyLabel,
  FACULTY_NOTE_MAX,
  type FacultyAnswerContext,
  type FaithfulLabel,
} from '@/lib/facultyLabels';

interface FacultyLabelPanelProps extends FacultyAnswerContext {
  onSubmitted?: () => void;
}

const FAITHFUL: { value: FaithfulLabel; label: string }[] = [
  { value: 'yes', label: 'Yes' },
  { value: 'partly', label: 'Partly' },
  { value: 'no', label: 'No' },
];

/**
 * Faculty reviewer labelling for one answer: faithful (yes/partly/no), safe
 * (yes/no), helpful (1-5) and a free-text note. Persisted via
 * `lib/facultyLabels` to Supabase (owner-scoped RLS), not localStorage.
 * Not for seekers: mount only for reviewers, never under crisis answers.
 */
export function FacultyLabelPanel({ onSubmitted, ...ctx }: FacultyLabelPanelProps) {
  const [faithful, setFaithful] = useState<FaithfulLabel | null>(null);
  const [safe, setSafe] = useState<boolean | null>(null);
  const [helpful, setHelpful] = useState<number | null>(null);
  const [note, setNote] = useState('');
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved'>('idle');
  const [error, setError] = useState<string | null>(null);

  const hasKey = Boolean(ctx.traceId || ctx.requestId);
  const ready = hasKey && faithful !== null && safe !== null && helpful !== null && status !== 'saving';

  const submit = async () => {
    if (faithful === null || safe === null || helpful === null) return;
    setStatus('saving');
    setError(null);
    try {
      const err = await submitFacultyLabel(ctx, { faithful, safe, helpful, note });
      if (err) {
        setError(err);
        setStatus('idle');
        return;
      }
      setStatus('saved');
      onSubmitted?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed');
      setStatus('idle');
    }
  };

  if (status === 'saved') {
    return (
      <div data-testid="faculty-label-saved" className="mt-2 text-[11px] text-muted-foreground">
        Label saved.
      </div>
    );
  }

  return (
    <div
      role="group"
      aria-label="Faculty label"
      className="mt-2 space-y-2 rounded-md border border-muted-foreground/20 p-2 text-[11px]"
    >
      <div role="radiogroup" aria-label="Faithful to the teachings" className="flex items-center gap-1">
        <span className="mr-1">Faithful</span>
        {FAITHFUL.map((o) => (
          <Button
            key={o.value}
            type="button"
            size="sm"
            variant={faithful === o.value ? 'default' : 'outline'}
            role="radio"
            aria-checked={faithful === o.value}
            className="h-6 px-2 text-[11px]"
            onClick={() => setFaithful(o.value)}
          >
            {o.label}
          </Button>
        ))}
      </div>
      <div role="radiogroup" aria-label="Safe" className="flex items-center gap-1">
        <span className="mr-1">Safe</span>
        {[true, false].map((v) => (
          <Button
            key={String(v)}
            type="button"
            size="sm"
            variant={safe === v ? 'default' : 'outline'}
            role="radio"
            aria-checked={safe === v}
            aria-label={v ? 'Safe yes' : 'Safe no'}
            className="h-6 px-2 text-[11px]"
            onClick={() => setSafe(v)}
          >
            {v ? 'Yes' : 'No'}
          </Button>
        ))}
      </div>
      <div role="radiogroup" aria-label="Helpful (1-5)" className="flex items-center gap-1">
        <span className="mr-1">Helpful</span>
        {[1, 2, 3, 4, 5].map((n) => (
          <Button
            key={n}
            type="button"
            size="sm"
            variant={helpful === n ? 'default' : 'outline'}
            role="radio"
            aria-checked={helpful === n}
            aria-label={`Helpful ${n}`}
            className="h-6 w-6 px-0 text-[11px]"
            onClick={() => setHelpful(n)}
          >
            {n}
          </Button>
        ))}
      </div>
      <textarea
        aria-label="Reviewer note"
        value={note}
        maxLength={FACULTY_NOTE_MAX}
        onChange={(e) => setNote(e.target.value)}
        rows={2}
        className="w-full rounded border border-muted-foreground/20 bg-background p-1 text-[11px]"
      />
      {!hasKey && <p role="alert">This answer has no trace id, so it cannot be labelled.</p>}
      {error && (
        <p role="alert" data-testid="faculty-label-error">
          Could not save label: {error}
        </p>
      )}
      <Button type="button" size="sm" className="h-6 px-2 text-[11px]" disabled={!ready} onClick={() => void submit()}>
        Save label
      </Button>
    </div>
  );
}
