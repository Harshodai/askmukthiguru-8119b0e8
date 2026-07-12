import { useTranslation } from 'react-i18next';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Mic, MicOff } from 'lucide-react';
import { recordMoodCheckIn, getMeditationStats } from '@/lib/meditationStorage';
import { practices } from '@/lib/practicesContent';
import { useVoiceInput } from '@/hooks/useVoiceInput';

export type MoodId = 'calm' | 'anxious' | 'sad' | 'frustrated' | 'open';

const MOODS: { id: MoodId; emoji: string }[] = [
  { id: 'calm', emoji: '😌' },
  { id: 'anxious', emoji: '😟' },
  { id: 'sad', emoji: '😢' },
  { id: 'frustrated', emoji: '😡' },
  { id: 'open', emoji: '✨' },
];

const MOOD_TO_PRACTICE: Record<MoodId, string> = {
  anxious: 'serene-mind',
  frustrated: 'serene-mind',
  sad: 'beautiful-state',
  calm: 'soul-sync',
  open: 'daily-reflection',
};

interface MoodCheckInProps {
  isOpen: boolean;
  onClose: () => void;
  micHook?: (() => {
    isListening: boolean;
    transcript: string;
    start: () => void;
    stop: () => void;
    error: string | null;
    reset: () => void;
    supported: boolean;
  }) | null;
}

export const MoodCheckIn = ({ isOpen, onClose, micHook = null }: MoodCheckInProps) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [mood, setMood] = useState<MoodId | null>(null);
  const [reflection, setReflection] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const voice = useVoiceInput();
  const mic = micHook ? micHook() : voice;

  const suggestedPractice = useMemo(() => {
    if (!mood) return undefined;
    const slug = MOOD_TO_PRACTICE[mood];
    return practices.find((p) => p.slug === slug);
  }, [mood]);

  const handleSubmit = async () => {
    if (!mood) return;
    await recordMoodCheckIn(mood, reflection.slice(0, 200) || undefined);
    setSubmitted(true);
  };

  const streakDays = useMemo(() => {
    if (!submitted) return 0;
    try { return getMeditationStats().streakDays ?? 0; } catch { return 0; }
  }, [submitted]);

  const handleStartPractice = () => {
    if (!suggestedPractice) return;
    onClose();
    navigate(`/practices/${suggestedPractice.slug}`);
  };

  useEffect(() => {
    if (mic.transcript) {
      setReflection((prev) => (prev + ' ' + mic.transcript).slice(0, 200).trim());
      mic.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mic.transcript]);

  const handleVoiceToggle = () => {
    if (mic.isListening) mic.stop();
    else mic.start();
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center"
          role="dialog"
          aria-modal="true"
          aria-label={t('mood.title')}
        >
          <div className="absolute inset-0 bg-background/95 backdrop-blur-xl" onClick={onClose} />
          <motion.div
            initial={{ opacity: 0, scale: 0.97, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 12 }}
            transition={{ type: 'spring', damping: 26, stiffness: 300 }}
            className="relative z-10 w-full max-w-md mx-4"
          >
            <div className="glass-card rounded-3xl bg-card/90 border border-border/40 shadow-2xl p-6 text-center">
              <button
                onClick={onClose}
                aria-label="Close"
                className="absolute top-3 right-3 p-2 rounded-full hover:bg-muted"
              >
                <X className="w-4 h-4 text-muted-foreground" />
              </button>
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ojas/85 mb-1">
                {t('mood.title')}
              </p>
              <h2 className="text-lg font-medium text-foreground mb-1">{t('mood.subtitle')}</h2>

              {!submitted ? (
                <>
                  <div className="flex justify-center gap-3 mt-5">
                    {MOODS.map((m) => (
                      <button
                        key={m.id}
                        onClick={() => setMood(m.id)}
                        aria-label={t(`mood.${m.id}`) || m.id.charAt(0).toUpperCase() + m.id.slice(1)}
                        aria-pressed={mood === m.id}
                        className={`text-3xl p-2 rounded-full transition-all ${
                          mood === m.id
                            ? 'bg-ojas/15 ring-2 ring-ojas scale-110'
                            : 'opacity-70 hover:opacity-100 hover:bg-muted/40'
                        }`}
                      >
                        <span aria-hidden>{m.emoji}</span>
                      </button>
                    ))}
                  </div>

                  <label className="block text-[10px] font-semibold text-muted-foreground/80 uppercase tracking-wider mt-5 mb-1 text-left">
                    {t('mood.reflectionLabel')}
                  </label>
                  <textarea
                    value={reflection}
                    onChange={(e) => setReflection(e.target.value.slice(0, 200))}
                    placeholder={t('mood.reflectionPlaceholder')}
                    rows={3}
                    className="w-full rounded-xl border border-border/50 bg-card p-3 text-sm focus:outline-none focus:ring-1 focus:ring-ojas/40"
                  />
                  <div className="flex justify-between items-center mt-1">
                    <button
                      type="button"
                      onClick={handleVoiceToggle}
                      disabled={!mic.supported}
                      aria-label={mic.isListening ? 'Stop voice input' : 'Start voice input'}
                      className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-ojas disabled:opacity-40"
                    >
                      {mic.isListening ? <MicOff className="w-3.5 h-3.5" /> : <Mic className="w-3.5 h-3.5" />}
                      {mic.isListening ? 'Listening' : 'Speak'}
                    </button>
                    <span className="text-[10px] text-muted-foreground">{reflection.length}/200</span>
                  </div>
                  {mic.error && (
                    <p className="text-[10px] text-destructive text-left mt-1">{mic.error}</p>
                  )}

                  {suggestedPractice && (
                    <div className="mt-4 p-3 rounded-2xl bg-ojas/5 border border-ojas/20 text-left">
                      <p className="text-[10px] font-semibold text-ojas uppercase tracking-wider mb-1">
                        {t('mood.suggestedPractice')}
                      </p>
                      <p className="text-sm font-medium text-foreground">{suggestedPractice.title}</p>
                    </div>
                  )}

                  <button
                    onClick={handleSubmit}
                    disabled={!mood}
                    className="mt-5 w-full py-2.5 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-md"
                  >
                    {t('mood.submit')}
                  </button>

                  {suggestedPractice && (
                    <button
                      onClick={handleStartPractice}
                      className="mt-2 text-xs text-ojas hover:text-ojas-light underline underline-offset-2"
                    >
                      {t('mood.startPractice')}
                    </button>
                  )}
                </>
              ) : (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="py-6"
                >
                  <p className="text-sm text-foreground">{t('mood.thanks')}</p>
                  {streakDays > 0 && (
                    <div className="mt-3 inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-ojas/10 border border-ojas/25 text-xs font-semibold text-ojas">
                      🔥 {streakDays} {streakDays === 1 ? 'day' : 'days'} streak — keep it going!
                    </div>
                  )}
                  {suggestedPractice && (
                    <button
                      onClick={handleStartPractice}
                      className="mt-4 px-4 py-2 rounded-full bg-ojas/90 hover:bg-ojas text-white text-sm font-semibold transition-all shadow-md"
                    >
                      {t('mood.startPractice')} →
                    </button>
                  )}
                </motion.div>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
