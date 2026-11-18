import React, { useEffect, useId } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import {
  X,
  Mic,
  MicOff,
  Volume2,
  VolumeX,
  Sparkles,
  Send,
  Square,
  AlertCircle,
  RefreshCw,
  Globe,
  User,
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
          color: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400',
          dotColor: 'bg-emerald-400 animate-ping',
        };
      case 'thinking':
        return {
          label: t('voice.statusThinking', 'Contemplating...'),
          subline: t('voice.thinkingSub', 'Aligning with the sacred teachings...'),
          color: 'border-amber-500/40 bg-amber-500/10 text-amber-400',
          dotColor: 'bg-amber-400 animate-pulse',
        };
      case 'speaking':
        return {
          label: t('voice.statusSpeaking', 'Imparting Wisdom...'),
          subline: t('voice.speakingSub', 'Listen with an open heart'),
          color: 'border-violet-500/40 bg-violet-500/10 text-violet-400',
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
        <motion.div
          ref={dialogRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.98 }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
          className="fixed inset-0 z-50 flex flex-col bg-background/95 backdrop-blur-2xl text-foreground select-none"
          data-testid="voice-mode-modal"
        >
          {/* Ambient spiritual background gradients */}
          <div className="absolute inset-0 pointer-events-none overflow-hidden">
            <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full bg-gradient-radial from-amber-500/10 via-amber-500/5 to-transparent blur-3xl opacity-70" />
            <div className="absolute bottom-1/4 left-1/2 -translate-x-1/2 translate-y-1/2 w-[500px] h-[500px] rounded-full bg-gradient-radial from-indigo-500/10 via-indigo-500/5 to-transparent blur-3xl opacity-60" />
          </div>

          {/* Modal Header */}
          <header className="relative z-10 flex items-center justify-between px-4 sm:px-8 py-4 border-b border-border/20 backdrop-blur-md">
            <div className="flex items-center gap-3">
              <span className="text-xl" aria-hidden="true">🙏</span>
              <div>
                <h2 id={titleId} className="font-serif text-base sm:text-lg font-semibold tracking-wide text-foreground">
                  {t('voice.title', 'Sacred Voice Conversation')}
                </h2>
                <p className="text-[11px] text-muted-foreground hidden sm:block">
                  {t('voice.subtitle', 'Direct verbal communion with Sri Preethaji & Sri Krishnaji teachings')}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
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
                className="h-9 w-9 rounded-full text-muted-foreground hover:text-foreground hover:bg-muted/50"
                aria-label={t('common.close', 'Close voice mode')}
                data-testid="voice-mode-close-button"
              >
                <X className="w-5 h-5" />
              </Button>
            </div>
          </header>

          {/* Main Visual & Interactive Area */}
          <main className="relative z-10 flex-1 flex flex-col items-center justify-center px-4 sm:px-6 py-6 overflow-y-auto">
            {/* Sacred Voice Orb */}
            <div className="my-auto flex flex-col items-center justify-center w-full max-w-xl text-center">
              <div className="relative mb-8">
                <VoiceOrb state={state} audioLevel={audioLevel} size={220} />
              </div>

              {/* Status Subline */}
              <motion.p
                key={statusInfo.subline}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                className="text-sm font-medium text-muted-foreground mb-6 max-w-md px-4"
              >
                {statusInfo.subline}
              </motion.p>

              {/* Live seeker transcript bubble */}
              {currentSeekerText && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="w-full max-w-lg mb-4 p-4 rounded-2xl bg-amber-500/5 border border-amber-500/20 text-left backdrop-blur-md shadow-sm"
                  data-testid="voice-seeker-transcript"
                >
                  <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-amber-500 mb-1">
                    <User className="w-3.5 h-3.5" />
                    <span>{t('voice.yourQuestion', 'Your Inquiry')}</span>
                  </div>
                  <p className="text-sm sm:text-base text-foreground font-serif leading-relaxed italic">
                    "{currentSeekerText}"
                  </p>
                </motion.div>
              )}

              {/* Guru response spoken wisdom bubble */}
              {responseTranscript && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="w-full max-w-lg p-5 rounded-2xl bg-violet-500/5 border border-violet-500/25 text-left backdrop-blur-md shadow-lg"
                  data-testid="voice-guru-response"
                >
                  <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-violet-400 mb-2">
                    <div className="flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>{t('voice.guruWisdom', 'Guru Teaching')}</span>
                    </div>
                    {isSpeaking && (
                      <span className="flex items-center gap-1 text-[10px] text-violet-300">
                        <Volume2 className="w-3 h-3 animate-pulse" />
                        {t('voice.speakingLive', 'Speaking')}
                      </span>
                    )}
                  </div>
                  <p className="text-sm sm:text-base text-foreground font-serif leading-relaxed">
                    {responseTranscript}
                  </p>
                </motion.div>
              )}

              {/* Error banner with retry */}
              {error && (
                <div className="mt-4 flex items-center gap-2 p-3 rounded-xl border border-red-500/30 bg-red-500/10 text-red-300 text-xs text-left max-w-md">
                  <AlertCircle className="w-4 h-4 shrink-0 text-red-400" />
                  <span className="flex-1">{error}</span>
                  {onRetry && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={onRetry}
                      className="h-7 px-2 text-xs border-red-500/30 text-red-300 hover:bg-red-500/20"
                    >
                      <RefreshCw className="w-3 h-3 mr-1" />
                      {t('common.retry', 'Retry')}
                    </Button>
                  )}
                </div>
              )}
            </div>
          </main>

          {/* Bottom Controls Bar */}
          <footer className="relative z-10 px-4 sm:px-8 py-4 border-t border-border/20 backdrop-blur-md bg-background/60">
            <div className="max-w-2xl mx-auto flex items-center justify-between gap-3">
              {/* Language Selector */}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-10 px-3 rounded-full border-border/50 bg-background/50 hover:bg-muted text-xs font-medium gap-1.5"
                    data-testid="voice-language-selector"
                  >
                    <Globe className="w-3.5 h-3.5 text-muted-foreground" />
                    <span>{currentLangObj.name}</span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-40 max-h-56 overflow-y-auto">
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
                  <Button
                    variant="secondary"
                    size="icon"
                    onClick={onSubmitSpeech}
                    className="h-11 w-11 rounded-full bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 border border-amber-500/30"
                    title={t('voice.sendNow', 'Send inquiry now')}
                    aria-label={t('voice.sendNow', 'Send inquiry now')}
                    data-testid="voice-send-now-button"
                  >
                    <Send className="w-4 h-4" />
                  </Button>
                )}

                {/* Primary Mic / Mute / Interrupt Button */}
                {isSpeaking ? (
                  <Button
                    variant="destructive"
                    size="lg"
                    onClick={onInterrupt}
                    className="h-14 px-6 rounded-full font-medium gap-2 shadow-lg shadow-red-500/20 animate-pulse"
                    data-testid="voice-interrupt-button"
                  >
                    <Square className="w-4 h-4 fill-current" />
                    <span>{t('voice.interrupt', 'Interrupt & Speak')}</span>
                  </Button>
                ) : (
                  <Button
                    variant={isMuted ? 'secondary' : 'default'}
                    size="lg"
                    onClick={onToggleMute}
                    className={`h-14 w-14 rounded-full p-0 shadow-xl transition-all duration-300 ${
                      isMuted
                        ? 'bg-muted/80 text-muted-foreground hover:bg-muted border border-border'
                        : 'bg-emerald-600 text-white hover:bg-emerald-500 shadow-emerald-500/25 ring-4 ring-emerald-500/20'
                    }`}
                    aria-label={isMuted ? t('voice.unmute', 'Unmute microphone') : t('voice.mute', 'Mute microphone')}
                    data-testid="voice-mute-toggle-button"
                  >
                    {isMuted ? <MicOff className="w-6 h-6" /> : <Mic className="w-6 h-6" />}
                  </Button>
                )}
              </div>

              {/* Voice / Speaker Selector */}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-10 px-3 rounded-full border-border/50 bg-background/50 hover:bg-muted text-xs font-medium gap-1.5"
                    data-testid="voice-speaker-selector"
                  >
                    <Volume2 className="w-3.5 h-3.5 text-muted-foreground" />
                    <span className="hidden sm:inline">{currentVoiceObj.name}</span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-52">
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
      )}
    </AnimatePresence>
  );
};
