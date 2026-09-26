import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Phone, Play } from 'lucide-react';
import { PublicShell } from '@/components/layout/PublicShell';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { BrandedSpinner } from '@/components/common/BrandedSpinner';
import { DiscourseVideoModal, type DiscourseCitation } from '@/components/chat/CitationCard';
import {
  queryFirstPerson,
  FirstPersonError,
  type FirstPersonErrorCode,
  type FirstPersonResponse,
  type FirstPersonCitation,
} from '@/lib/firstPersonService';
import { mapFirstPersonCitationToDiscourseCitation } from '@/lib/firstPersonCitationMapper';

// Mirrors backend/app/api/first_person.py FirstPersonQueryRequest.query (max_length=2000).
const MAX_QUERY_LENGTH = 2000;

const ERROR_MESSAGES: Record<FirstPersonErrorCode, string> = {
  disabled: "This feature isn't enabled on this deployment yet.",
  rate_limited: 'Too many requests — please wait a moment and try again.',
  unavailable: 'This feature is temporarily unavailable. Please try again shortly.',
  invalid_response: 'Something unexpected happened. Please try again.',
  network: 'Could not reach the backend. Check your connection and try again.',
};

interface ErrorState {
  code: FirstPersonErrorCode;
  message: string;
  retryAfterSeconds?: number;
}

function formatClock(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s < 10 ? '0' : ''}${s}`;
}

export default function TeacherWords() {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<FirstPersonResponse | null>(null);
  const [errorState, setErrorState] = useState<ErrorState | null>(null);
  const [secondsRemaining, setSecondsRemaining] = useState(0);
  const [openCitation, setOpenCitation] = useState<DiscourseCitation | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);
  const lastQueryRef = useRef('');
  const resultsHeadingRef = useRef<HTMLHeadingElement>(null);

  // Countdown for rate_limited retries — ticks every second until the
  // server-given wait has elapsed, then re-enables Retry.
  useEffect(() => {
    if (errorState?.code !== 'rate_limited' || !errorState.retryAfterSeconds) {
      setSecondsRemaining(0);
      return;
    }
    setSecondsRemaining(errorState.retryAfterSeconds);
    const interval = setInterval(() => {
      setSecondsRemaining((s) => (s <= 1 ? 0 : s - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, [errorState]);

  // Move focus to the results heading once a response lands, so screen
  // reader / keyboard users land on the new content instead of the form.
  useEffect(() => {
    if (!loading && result) {
      resultsHeadingRef.current?.focus();
    }
  }, [loading, result]);

  const runQuery = async (text: string) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const requestId = ++requestIdRef.current;

    lastQueryRef.current = text;
    setLoading(true);
    setErrorState(null);
    setResult(null);

    try {
      const response = await queryFirstPerson(text, { signal: controller.signal });
      if (requestIdRef.current !== requestId) return; // a newer request supersedes this one
      setResult(response);
    } catch (err) {
      if (requestIdRef.current !== requestId) return;
      if (err instanceof DOMException && err.name === 'AbortError') return; // intentionally superseded
      if (err instanceof FirstPersonError) {
        setErrorState({
          code: err.code,
          message: ERROR_MESSAGES[err.code] ?? err.message,
          retryAfterSeconds: err.retryAfterSeconds,
        });
      } else {
        setErrorState({ code: 'unavailable', message: 'Something unexpected happened. Please try again.' });
      }
    } finally {
      if (requestIdRef.current === requestId) setLoading(false);
    }
  };

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || trimmed.length > MAX_QUERY_LENGTH) return;
    // Deliberately not gated on `loading`: submitting again while a request is
    // still in flight (e.g. the seeker edits and re-asks) aborts the stale
    // one via runQuery's AbortController + request-id guard, rather than
    // being blocked outright.
    void runQuery(trimmed);
  };

  const retryDisabled = loading || (errorState?.code === 'rate_limited' && secondsRemaining > 0);

  return (
    <PublicShell>
      <div className="mx-auto max-w-2xl px-4 py-10 sm:py-16">
        <h1 className="font-serif text-2xl font-semibold text-foreground sm:text-3xl">
          In the Teacher&apos;s Own Words
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Ask a question and hear Sri Preethaji or Sri Krishnaji&apos;s exact recorded words, at
          the exact moment they were spoken — never a paraphrase, never AI-written text presented
          as theirs.
        </p>

        <form onSubmit={handleSubmit} className="mt-6 space-y-3">
          <Label htmlFor="teacher-words-query">Your question</Label>
          <Textarea
            id="teacher-words-query"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. What is the Beautiful State?"
            rows={3}
            maxLength={MAX_QUERY_LENGTH}
          />
          <Button type="submit" disabled={!query.trim()}>
            {loading ? 'Searching…' : 'Ask'}
          </Button>
        </form>

        <div className="mt-8" aria-live="polite">
          {loading && <BrandedSpinner />}

          {!loading && errorState && (
            <Alert variant="destructive">
              <AlertDescription>
                {errorState.code === 'rate_limited' && secondsRemaining > 0
                  ? `${errorState.message} You can retry in ${secondsRemaining}s.`
                  : errorState.message}
              </AlertDescription>
              {errorState.code !== 'disabled' && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="mt-3"
                  disabled={retryDisabled}
                  onClick={() => void runQuery(lastQueryRef.current)}
                >
                  Retry
                </Button>
              )}
            </Alert>
          )}

          {!loading && result && (
            <TeacherWordsResult result={result} onPlay={setOpenCitation} headingRef={resultsHeadingRef} />
          )}
        </div>
      </div>

      <DiscourseVideoModal
        isOpen={openCitation !== null}
        onClose={() => setOpenCitation(null)}
        citation={openCitation}
      />
    </PublicShell>
  );
}

function TeacherWordsResult({
  result,
  onPlay,
  headingRef,
}: {
  result: FirstPersonResponse;
  onPlay: (citation: DiscourseCitation) => void;
  headingRef: React.RefObject<HTMLHeadingElement>;
}) {
  if (result.status === 'crisis_redirect') {
    return (
      <div
        ref={headingRef as unknown as React.RefObject<HTMLDivElement>}
        tabIndex={-1}
        role="alert"
        aria-live="assertive"
        className="whitespace-pre-wrap rounded-xl border-2 border-destructive bg-destructive/10 p-5 text-base font-medium text-foreground focus:outline-none"
      >
        <div className="mb-2 flex items-center gap-2 font-semibold text-destructive">
          <Phone className="h-5 w-5" aria-hidden="true" />
          Please reach out for support
        </div>
        {result.answer_text}
      </div>
    );
  }

  if (result.status === 'abstained') {
    return (
      <p
        ref={headingRef as unknown as React.RefObject<HTMLParagraphElement>}
        tabIndex={-1}
        className="rounded-lg border border-border/50 bg-muted/30 p-4 text-sm text-muted-foreground focus:outline-none"
      >
        {result.answer_text}
      </p>
    );
  }

  if (result.status === 'error') {
    return (
      <p
        ref={headingRef as unknown as React.RefObject<HTMLParagraphElement>}
        tabIndex={-1}
        role="alert"
        className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive focus:outline-none"
      >
        {result.error || 'Something went wrong retrieving these teachings.'}
      </p>
    );
  }

  // success | weak_match
  return (
    <div className="space-y-4">
      <h2
        ref={headingRef}
        tabIndex={-1}
        className="font-serif text-lg font-semibold text-foreground focus:outline-none"
      >
        Teachings found
      </h2>
      {!result.is_direct_answer && (
        <Badge variant="outline" className="border-amber-500/50 text-amber-600">
          Related, not a direct answer
        </Badge>
      )}
      {result.citations.map((citation, i) => (
        <ClipCard key={`${citation.video_id}-${citation.start_ms}`} citation={citation} index={i + 1} onPlay={onPlay} />
      ))}
    </div>
  );
}

function ClipCard({
  citation,
  index,
  onPlay,
}: {
  citation: FirstPersonCitation;
  index: number;
  onPlay: (citation: DiscourseCitation) => void;
}) {
  const clockLabel = formatClock(citation.timestamp_seconds);
  const playbackLabel =
    citation.playback_start_seconds != null ? `from ${formatClock(citation.playback_start_seconds)}` : null;

  return (
    <Card className="p-4">
      <blockquote className="border-l-2 border-saffron-gold/40 pl-3 font-serif text-base italic text-foreground">
        &quot;{citation.verbatim_text}&quot;
      </blockquote>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        {/* The real speaker from the response — never hardcoded. */}
        <span className="font-medium text-saffron-gold">{citation.speaker}</span>
        <span>{clockLabel}</span>
        {playbackLabel && <span>({playbackLabel})</span>}
        {citation.caption_status === 'auto_transcript' && (
          <Badge variant="secondary" className="text-[10px]">
            auto transcript
          </Badge>
        )}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="ml-auto gap-1"
          aria-label={`Play clip: ${citation.speaker} at ${clockLabel}`}
          onClick={() => onPlay(mapFirstPersonCitationToDiscourseCitation(citation, index))}
        >
          <Play className="h-3 w-3 fill-current" /> Play clip
        </Button>
      </div>
    </Card>
  );
}
