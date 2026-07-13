import { useEffect, useState } from 'react';
import { Check, Pause, Play, RotateCcw, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useDailyTeaching } from '@/hooks/useDailyTeaching';
import { FlashcardPractice } from './FlashcardPractice';

const REFLECTION_SECONDS = 3 * 60;
const FALLBACK_PROMPT = 'Take a quiet moment to notice what is present in you right now. Let one breath arrive and leave without needing to change anything.';

const formatTime = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;

export const WisdomReflectionPractice = () => {
  const { teaching, loading } = useDailyTeaching();
  const [secondsLeft, setSecondsLeft] = useState(REFLECTION_SECONDS);
  const [isRunning, setIsRunning] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [checkIn, setCheckIn] = useState<string | null>(null);

  useEffect(() => {
    if (!isRunning || secondsLeft === 0) return;
    const timer = window.setInterval(() => {
      setSecondsLeft((seconds) => Math.max(0, seconds - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [isRunning, secondsLeft]);

  useEffect(() => {
    if (secondsLeft === 0) {
      setIsRunning(false);
      setCompleted(true);
    }
  }, [secondsLeft]);

  const hasTeachingText = Boolean(teaching?.caption?.trim());
  const sourceText = hasTeachingText ? teaching.caption : FALLBACK_PROMPT;
  const sourceLabel = loading
    ? null
    : hasTeachingText
    ? 'Source: Daily Teaching — Sri Preethaji & Sri Krishnaji'
    : 'Source: Reflection prompt — shown because no active Daily Teaching is available';

  const restart = () => {
    setSecondsLeft(REFLECTION_SECONDS);
    setIsRunning(false);
    setCompleted(false);
    setCheckIn(null);
  };

  return (
    <section className="space-y-6" aria-labelledby="wisdom-reflection-heading">
      <Card className="border-ojas/20">
        <CardHeader>
          <CardTitle id="wisdom-reflection-heading" className="flex items-center gap-2 text-base">
            <Sparkles className="w-5 h-5 text-ojas" aria-hidden="true" /> Source teaching
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {loading ? (
            <p className="text-sm text-muted-foreground" aria-live="polite">Loading today&apos;s teaching…</p>
          ) : (
            <p className="font-serif text-lg leading-relaxed text-foreground/90">{sourceText}</p>
          )}
          {sourceLabel && <p className="text-xs text-muted-foreground">{sourceLabel}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Three-minute reflection</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <ol className="space-y-2 list-decimal list-inside text-sm leading-relaxed text-foreground/90">
            <li>Read the teaching once, slowly.</li>
            <li>Rest with one word or idea that feels alive for you.</li>
            <li>Notice breath, body, and mind without trying to fix them.</li>
          </ol>
          <div className="rounded-lg bg-muted px-4 py-3 flex flex-wrap items-center justify-between gap-3">
            <span className="font-mono text-2xl tabular-nums" aria-label={`${formatTime(secondsLeft)} remaining`}>
              {formatTime(secondsLeft)}
            </span>
            <div className="flex gap-2">
              <Button type="button" onClick={() => setIsRunning((running) => !running)} disabled={completed}>
                {isRunning ? <Pause className="w-4 h-4 mr-2" /> : <Play className="w-4 h-4 mr-2" />}
                {isRunning ? 'Pause' : 'Begin'}
              </Button>
              <Button type="button" variant="outline" onClick={restart}>
                <RotateCcw className="w-4 h-4 mr-2" /> Reset
              </Button>
            </div>
          </div>
          {!completed && (
            <Button type="button" variant="ghost" className="px-0" onClick={() => { setIsRunning(false); setCompleted(true); }}>
              I&apos;m ready to check in
            </Button>
          )}
          {completed && <p className="text-sm text-muted-foreground" role="status">Reflection complete. You can check in when ready.</p>}
        </CardContent>
      </Card>

      {completed && (
        <Card aria-labelledby="reflection-check-in">
          <CardHeader>
            <CardTitle id="reflection-check-in" className="text-base">How are you now?</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-2" role="group" aria-label="Post-practice check-in">
              {['More settled', 'About the same', 'Still carrying a lot'].map((option) => (
                <Button
                  key={option}
                  type="button"
                  variant={checkIn === option ? 'default' : 'outline'}
                  aria-pressed={checkIn === option}
                  onClick={() => setCheckIn(option)}
                >
                  {checkIn === option && <Check className="w-4 h-4 mr-2" />}
                  {option}
                </Button>
              ))}
            </div>
            {checkIn && <p className="text-sm text-muted-foreground" role="status">Thank you for noticing. No answer needs to be different.</p>}
          </CardContent>
        </Card>
      )}

      {/* Spaced Repetition Active Recall Widget */}
      <FlashcardPractice />
    </section>
  );
};
