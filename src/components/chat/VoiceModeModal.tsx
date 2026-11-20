import React, { useId } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import {
  X,
  Mic,
  MicOff,
  Volume2,
  Sprout,
  Send,
  Square,
  AlertCircle,
  RefreshCw,
  Globe,
  User,
  Quote,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { VoiceOrb } from './VoiceOrb';
import { useDialogFocus } from '@/hooks/useDialogFocus';
import { LANGUAGES } from './LanguageSelector';
import type { VoiceConversationState } from '@/hooks/useVoiceConversation';
import { TEACHERS_DISPLAY_NAME } from '@/lib/greetingConstants';

export interface VoiceModeModalProps {
  isOpen: boolean;
  onClose: () => void;
  state: VoiceConversationState;
  transcript: string;
  interimTranscript: string;
  responseTranscript: string;
  audioLevel: number;
  isMuted: boolean;
  isSpeaking: boolean;
  error: string | null;
  currentLanguage: string;
  currentSpeaker: string;
  onToggleMute: () => void;
  onInterrupt: () => void;
  onSubmitSpeech: () => void;
  onLanguageChange: (lang: string) => void;
  onSpeakerChange: (speaker: string) => void;
  onRetry?: () => void;
}

const SARVAM_VOICES = [
  { id: 'priya', name: 'Priya', desc: 'Devotional & Warm (Female)' },
  { id: 'ishita', name: 'Ishita', desc: 'Clear & Serene (Female)' },
  { id: 'shubh', name: 'Shubh', desc: 'Deep & Grounded (Male)' },
  { id: 'mani', name: 'Mani', desc: 'Calm & Resonant (Male)' },
];

export const VoiceModeModal: React.FC<VoiceModeModalProps> = ({
  isOpen,
  onClose,
  state,
  transcript,
  interimTranscript,
  responseTranscript,
  audioLevel,
  isMuted,
  isSpeaking,
  error,
  currentLanguage,
  currentSpeaker,
  onToggleMute,
  onInterrupt,
  onSubmitSpeech,
  onLanguageChange,
  onSpeakerChange,
  onRetry,
}) => {
  const { t } = useTranslation();
  const dialogRef = useDialogFocus<HTMLDivElement>(isOpen, { onEscape: onClose });
  const titleId = useId();

  // Full seeker live text
  const currentSeekerText = (transcript + ' ' + interimTranscript).trim();

  // Status badge label and styles
  const getStatusInfo = () => {
    if (error) {
      return {
        label: t('voice.statusError', 'Attention Needed'),
        subline: error,
        color: 'border-red-500/40 bg-red-500/10 text-red-400',
        dotColor: 'bg-red-500',
      };
    }
    if (isMuted) {
      return {
        label: t('voice.statusMuted', 'Microphone Muted'),
        subline: t('voice.statusMutedSub', 'Tap microphone below to resume'),
        color: 'border-muted-foreground/30 bg-muted/20 text-muted-foreground',
        dotColor: 'bg-muted-foreground',
      };
    }
    switch (state) {
      case 'listening':
        return {
          label: t('voice.statusListening', 'Listening...'),
          subline: currentSeekerText
            ? t('voice.hearingYou', 'Hearing your prayer...')
            : t('voice.speakPrompt', 'Speak freely from your heart. The Guru is listening.'),
          color: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400 dark:text-emerald-300',
          dotColor: 'bg-emerald-400 animate-ping',
        };
      case 'thinking':
        return {
          label: t('voice.statusThinking', 'Contemplating...'),
          subline: t('voice.thinkingSub', 'Aligning with the sacred teachings...'),
          color: 'border-amber-500/40 bg-amber-500/10 text-amber-400 dark:text-amber-300',
          dotColor: 'bg-amber-400 animate-pulse',
        };
      case 'speaking':
        return {
          label: t('voice.statusSpeaking', 'Imparting Wisdom...'),
          subline: t('voice.speakingSub', 'Listen with an open heart'),
          color: 'border-violet-500/40 bg-violet-500/10 text-violet-400 dark:text-violet-300',
          dotColor: 'bg-violet-400 animate-pulse',
        };
      case 'idle':
      default:
        return {
          label: t('voice.statusReady', 'Ready'),
          subline: t('voice.readySub', 'Tap microphone to speak'),
          color: 'border-border/50 bg-background/50 text-foreground',
          dotColor: 'bg-foreground/50',
        };
    }
  };

  const statusInfo = getStatusInfo();
  const currentLangObj = LANGUAGES.find((l) => l.code === currentLanguage) || LANGUAGES[0];
  const currentVoiceObj = SARVAM_VOICES.find((v) => v.id === currentSpeaker) || SARVAM_VOICES[0];

  return (
    <AnimatePresence>
      {isOpen && (
        <div
          ref={dialogRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          className="fixed inset-0 z-[200] flex flex-col h-[100dvh] min-h-[100dvh] max-h-[100dvh] bg-background/95 backdrop-blur-3xl text-foreground select-none overflow-hidden"
          data-testid="voice-mode-modal"
        >
          {/* Ambient sacred spiritual gradients */}
          <div className="absolute inset-0 pointer-events-none overflow-hidden">
            <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[700px] rounded-full bg-gradient-radial from-amber-500/15 via-amber-500/5 to-transparent blur-3xl opacity-80" />
            <div className="absolute bottom-1/4 left-1/2 -translate-x-1/2 translate-y-1/2 w-[600px] h-[600px] rounded-full bg-gradient-radial from-violet-600/15 via-indigo-500/5 to-transparent blur-3xl opacity-75" />
            <div className="absolute top-1/2 left-1/4 w-[350px] h-[350px] rounded-full bg-gradient-radial from-amber-400/8 to-transparent blur-2xl" />
          </div>

          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.28, ease: [0.32, 0.72, 0, 1] }}
            className="relative z-10 flex flex-col flex-1 h-full"
          >
            {/* Modal Header: Frosted Glass Double-Bezel Bar */}
            <header className="flex-none flex items-center justify-between px-4 sm:px-8 py-3.5 sm:py-4 border-b border-white/10 dark:border-white/5 bg-card/60 backdrop-blur-xl">
              <div className="flex items-center gap-3">
                <div className="relative flex items-center justify-center w-9 h-9 rounded-full overflow-hidden border border-amber-400/40 shadow-[0_0_12px_rgba(245,158,11,0.3)] ring-1 ring-amber-400/20 bg-background shrink-0">
                  <img
                    src="/images/ekam-golden-orb-lotus-square.png"
                    alt="Ekam Golden Orb"
                    className="w-full h-full object-cover"
                  />
                </div>
                <div>
                  <h2 id={titleId} className="font-serif text-base sm:text-lg font-semibold tracking-wide text-foreground">
                    {t('voice.title', 'Sacred Voice Conversation')}
                  </h2>
                  <p className="text-[11px] text-muted-foreground hidden sm:block">
                    {t('voice.subtitle', `Direct verbal communion with ${TEACHERS_DISPLAY_NAME} teachings`)}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2 sm:gap-3">
                {/* Status pill */}
                <div
                  className={`flex items-center gap-2 px-3 py-1 rounded-full border text-xs font-medium backdrop-blur-md transition-colors ${statusInfo.color}`}
                  role="status"
                  aria-live="polite"
                >
                  <span className={`w-2 h-2 rounded-full ${statusInfo.dotColor}`} />
                  <span>{statusInfo.label}</span>
                </div>

                {/* Close Button */}
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={onClose}
                  className="h-10 w-10 min-h-[44px] min-w-[44px] rounded-full text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
                  aria-label={t('common.close', 'Close voice mode')}
                  data-testid="voice-mode-close-button"
                >
                  <X className="w-5 h-5" />
                </Button>
              </div>
            </header>

            {/* Main Visual & Interactive Sanctuary Area */}
            <main className="flex-1 flex flex-col items-center justify-center px-4 sm:px-6 py-4 sm:py-6 overflow-y-auto overscroll-contain">
              <div className="my-auto flex flex-col items-center justify-center w-full max-w-xl text-center">
                {/* Celestial Voice Orb */}
                <div className="relative mb-6 sm:mb-8">
                  <VoiceOrb state={state} audioLevel={audioLevel} size={220} />
                </div>

                {/* Status Subline */}
                <motion.p
                  key={statusInfo.subline}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3 }}
                  className="text-xs sm:text-sm font-medium text-muted-foreground mb-6 max-w-md px-4 leading-relaxed"
                >
                  {statusInfo.subline}
                </motion.p>

                {/* Live Seeker Transcript Bubble: Double-Bezel Card */}
                {currentSeekerText && (
                  <motion.div
                    initial={{ opacity: 0, y: 8, scale: 0.98 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    transition={{ duration: 0.25, ease: 'easeOut' }}
                    className="w-full max-w-lg mb-4 p-4 sm:p-5 rounded-2xl bg-amber-500/10 border border-amber-500/25 text-left backdrop-blur-xl shadow-lg relative overflow-hidden"
                    data-testid="voice-seeker-transcript"
                  >
                    <div className="absolute top-2 right-3 opacity-15 text-amber-500 pointer-events-none">
                      <Quote className="w-12 h-12" />
                    </div>
                    <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-amber-500 dark:text-amber-400 mb-1.5">
                      <User className="w-3.5 h-3.5" />
                      <span>{t('voice.yourQuestion', 'Your Inquiry')}</span>
                    </div>
                    <p className="text-sm sm:text-base text-foreground font-serif leading-relaxed italic">
                      "{currentSeekerText}"
                    </p>
                  </motion.div>
                )}

                {/* Guru Response Spoken Wisdom Bubble: Double-Bezel Sanctuary Card */}
                {responseTranscript && (
                  <motion.div
                    initial={{ opacity: 0, y: 12, scale: 0.98 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    transition={{ duration: 0.35, ease: 'easeOut' }}
                    className="w-full max-w-lg p-5 sm:p-6 rounded-2xl bg-violet-950/20 dark:bg-violet-950/30 border border-violet-500/30 text-left backdrop-blur-xl shadow-2xl relative overflow-hidden"
                    data-testid="voice-guru-response"
                  >
                    <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-violet-400 dark:text-violet-300 mb-2.5">
                      <div className="flex items-center gap-1.5">
                        <Sprout className="w-3.5 h-3.5 text-violet-400" />
                        <span>{t('voice.guruWisdom', 'Guru Teaching')}</span>
                      </div>
                      {isSpeaking && (
                        <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-violet-500/20 border border-violet-500/30 text-[10px] text-violet-300">
                          <Volume2 className="w-3 h-3 animate-pulse text-violet-300" />
                          {t('voice.speakingLive', 'Speaking')}
                        </span>
                      )}
                    </div>
                    <p className="text-sm sm:text-base text-foreground font-serif leading-relaxed">
                      {responseTranscript}
                    </p>
                  </motion.div>
                )}

                {/* Error Banner with Retry */}
                {error && (
                  <div className="mt-4 flex items-center gap-2 p-3.5 rounded-xl border border-red-500/35 bg-red-500/10 text-red-300 text-xs text-left max-w-md backdrop-blur-md">
                    <AlertCircle className="w-4 h-4 shrink-0 text-red-400" />
                    <span className="flex-1">{error}</span>
                    {onRetry && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={onRetry}
                        className="h-8 px-2.5 text-xs border-red-500/40 text-red-300 hover:bg-red-500/20 rounded-lg min-h-[36px]"
                      >
                        <RefreshCw className="w-3 h-3 mr-1" />
                        {t('common.retry', 'Retry')}
                      </Button>
                    )}
                  </div>
                )}
              </div>
            </main>

            {/* Bottom Controls Bar: Floating Frosted Glass Capsule */}
            <footer className="flex-none px-4 sm:px-8 py-3 sm:py-4 pb-[calc(env(safe-area-inset-bottom,0px)+0.75rem)]">
              <div className="max-w-xl mx-auto flex items-center justify-between gap-3 px-4 py-2.5 rounded-2xl border border-white/15 dark:border-white/10 bg-card/75 backdrop-blur-2xl shadow-2xl">
                {/* Language Selector */}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-11 px-3.5 min-h-[44px] rounded-xl border-border/60 bg-background/60 hover:bg-muted text-xs font-medium gap-1.5 transition-colors"
                      data-testid="voice-language-selector"
                    >
                      <Globe className="w-4 h-4 text-muted-foreground" />
                      <span>{currentLangObj.name}</span>
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="w-44 max-h-56 overflow-y-auto z-[210]">
                    {LANGUAGES.map((lang) => (
                      <DropdownMenuItem
                        key={lang.code}
                        onClick={() => onLanguageChange(lang.code)}
                        className={currentLanguage === lang.code ? 'font-semibold text-ojas' : ''}
                      >
                        {lang.name}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>

                {/* Central Action Controls */}
                <div className="flex items-center gap-3">
                  {/* Submit speech now button (visible when text is accumulated) */}
                  {currentSeekerText && state === 'listening' && (
                    <motion.div
                      initial={{ scale: 0.8, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0.8, opacity: 0 }}
                    >
                      <Button
                        variant="secondary"
                        size="icon"
                        onClick={onSubmitSpeech}
                        className="h-12 w-12 min-h-[44px] min-w-[44px] rounded-full bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 border border-amber-500/40 shadow-lg shadow-amber-500/10"
                        title={t('voice.sendNow', 'Send inquiry now')}
                        aria-label={t('voice.sendNow', 'Send inquiry now')}
                        data-testid="voice-send-now-button"
                      >
                        <Send className="w-4 h-4" />
                      </Button>
                    </motion.div>
                  )}

                  {/* Primary Mic / Mute / Interrupt Button */}
                  {isSpeaking ? (
                    <Button
                      variant="destructive"
                      size="lg"
                      onClick={onInterrupt}
                      className="h-14 px-6 min-h-[44px] rounded-full font-medium gap-2 shadow-xl shadow-red-500/25 animate-pulse"
                      data-testid="voice-interrupt-button"
                    >
                      <Square className="w-4 h-4 fill-current" />
                      <span className="text-xs sm:text-sm">{t('voice.interrupt', 'Interrupt & Speak')}</span>
                    </Button>
                  ) : (
                    <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.94 }}>
                      <Button
                        variant={isMuted ? 'secondary' : 'default'}
                        size="lg"
                        onClick={onToggleMute}
                        className={`h-14 w-14 min-h-[44px] min-w-[44px] rounded-full p-0 shadow-2xl transition-all duration-300 ${
                          isMuted
                            ? 'bg-muted/80 text-muted-foreground hover:bg-muted border border-border'
                            : 'bg-emerald-600 text-white hover:bg-emerald-500 shadow-emerald-500/30 ring-4 ring-emerald-500/20'
                        }`}
                        aria-label={isMuted ? t('voice.unmute', 'Unmute microphone') : t('voice.mute', 'Mute microphone')}
                        data-testid="voice-mute-toggle-button"
                      >
                        {isMuted ? <MicOff className="w-6 h-6" /> : <Mic className="w-6 h-6" />}
                      </Button>
                    </motion.div>
                  )}
                </div>

                {/* Voice / Speaker Selector */}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-11 px-3.5 min-h-[44px] rounded-xl border-border/60 bg-background/60 hover:bg-muted text-xs font-medium gap-1.5 transition-colors"
                      data-testid="voice-speaker-selector"
                    >
                      <Volume2 className="w-4 h-4 text-muted-foreground" />
                      <span className="hidden sm:inline">{currentVoiceObj.name}</span>
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-52 z-[210]">
                    {SARVAM_VOICES.map((voice) => (
                      <DropdownMenuItem
                        key={voice.id}
                        onClick={() => onSpeakerChange(voice.id)}
                        className={currentSpeaker === voice.id ? 'font-semibold text-ojas' : ''}
                      >
                        <div className="flex flex-col">
                          <span>{voice.name}</span>
                          <span className="text-[10px] text-muted-foreground">{voice.desc}</span>
                        </div>
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </footer>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};
