import { motion, AnimatePresence } from 'framer-motion';
import {
  Send, Square, Flame, Sparkles, Plus, Mic, Volume2,
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { LanguageSelector } from './LanguageSelector';
import { AssistantSwitcher } from './AssistantSwitcher';
import { ThinkingPills, type PipelineStep } from './ThinkingPills';
import { SlashCommandMenu, type SlashCommandId } from './SlashCommandMenu';

interface ChatComposerProps {
  inputValue: string;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  onInputChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  onSubmit: (e?: React.FormEvent) => void;
  onStop: () => void;
  isTyping: boolean;
  isStreaming: boolean;
  isAwaitingSereneMind: boolean;
  isListening: boolean;
  currentLanguage: string;
  voiceEnabled: boolean;
  ttsEnabled: boolean;
  isSpeaking: boolean;
  inputFocused: boolean;
  showPipeline: boolean;
  pipelineSteps: PipelineStep[];
  pipelineHeartbeat: boolean;
  showInstantPill: boolean;
  isLandingMode: boolean;
  onVoiceToggle: () => void;
  onTtsToggle: () => void;
  onLanguageChange: (code: string) => void;
  onSereneMind: () => void;
  onGuidedMeditation: () => void;
  onFocus: () => void;
  onBlur: () => void;
  onSlashCommand: (cmd: SlashCommandId) => void;
}

export function ChatComposer({
  inputValue,
  inputRef,
  onInputChange,
  onKeyDown,
  onSubmit,
  onStop,
  isTyping,
  isStreaming,
  isAwaitingSereneMind,
  isListening,
  currentLanguage,
  voiceEnabled,
  ttsEnabled,
  isSpeaking,
  inputFocused,
  showPipeline,
  pipelineSteps,
  pipelineHeartbeat,
  showInstantPill,
  isLandingMode,
  onVoiceToggle,
  onTtsToggle,
  onLanguageChange,
  onSereneMind,
  onGuidedMeditation,
  onFocus,
  onBlur,
  onSlashCommand,
}: ChatComposerProps) {
  const showThinking =
    showInstantPill || showPipeline || isTyping || (isStreaming && inputValue === '');

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(e);
  };

  return (
    <motion.div
      layoutId="chat-composer"
      className="w-full max-w-3xl mx-auto"
    >
      <form
        onSubmit={handleFormSubmit}
        role="form"
        aria-label="Message composer"
        className={`rounded-3xl border bg-card/70 backdrop-blur-md transition-all duration-300 ${
          inputFocused || isListening
            ? 'border-ojas/40 shadow-lg shadow-ojas/5'
            : 'border-border/60'
        }`}
      >
        {isAwaitingSereneMind && (
          <div className="flex items-center justify-between px-5 pt-4 pb-2 border-b border-border/40 bg-ojas/5 rounded-t-3xl">
            <span className="text-xs text-ojas font-medium">
              Please do Serene Mind now to unlock the chat.
            </span>
            <button
              type="button"
              onClick={onSereneMind}
              className="px-3 py-1 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground text-xs font-semibold hover:shadow-md transition-all"
            >
              Open Serene Mind
            </button>
          </div>
        )}

        {/* Slash command palette */}
        <div className="px-5 pt-3">
          <SlashCommandMenu
            input={inputValue}
            open={inputValue.startsWith('/')}
            onSelect={onSlashCommand}
            onClose={() => {
              const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLTextAreaElement.prototype, 'value'
              )?.set;
              if (nativeInputValueSetter && inputRef.current) {
                nativeInputValueSetter.call(inputRef.current, '');
                inputRef.current.dispatchEvent(new Event('input', { bubbles: true }));
              }
            }}
          />
        </div>

        <div className="px-5 pt-4 pb-2">
          <textarea
            ref={inputRef as React.Ref<HTMLTextAreaElement>}
            value={inputValue}
            onChange={onInputChange}
            onKeyDown={onKeyDown}
            onFocus={onFocus}
            onBlur={onBlur}
            placeholder={
              isAwaitingSereneMind
                ? 'Do Serene Mind now (say "open Serene Mind" to begin)…'
                : isListening
                  ? 'Speak now…'
                  : "Share what's on your heart…"
            }
            rows={1}
            aria-label="Your message"
            className="w-full bg-transparent border-none outline-none resize-none text-foreground placeholder:text-muted-foreground/60 text-[15px] leading-relaxed max-h-32 scrollbar-spiritual disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ minHeight: '28px' }}
            disabled={isAwaitingSereneMind}
          />
        </div>

        <div className="flex items-center gap-1.5 px-3 pb-3">
          <div className="flex items-center gap-1">
            <AssistantSwitcher variant="chip" />

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 rounded-full text-muted-foreground hover:text-foreground"
                  aria-label="More actions"
                >
                  <Plus className="w-4 h-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" side="top" className="w-48">
                <DropdownMenuItem onClick={onSereneMind}>
                  <Flame className="w-4 h-4 mr-2 text-ojas" />
                  Serene Mind
                </DropdownMenuItem>
                <DropdownMenuItem onClick={onGuidedMeditation}>
                  <Sparkles className="w-4 h-4 mr-2 text-ojas" />
                  Guided Meditation
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <LanguageSelector
              value={currentLanguage}
              voiceEnabled={voiceEnabled}
              isListening={isListening}
              onVoiceToggle={onVoiceToggle}
              onLanguageChange={onLanguageChange}
              ttsEnabled={ttsEnabled}
              onTtsToggle={onTtsToggle}
              isSpeaking={isSpeaking}
              compact
            />
          </div>

          <div className="flex-1" />

          <div className="flex items-center gap-1">

            {/* Always-visible mic — voice input was buried in the language dropdown */}
            {(
              <Button
                type="button"
                size="icon"
                variant="ghost"
                onClick={onVoiceToggle}
                aria-label={isListening ? 'Stop voice input' : 'Speak your question'}
                aria-pressed={isListening}
                title={isListening ? 'Stop listening' : 'Speak your question'}
                className={`h-8 w-8 rounded-full transition-all ${
                  isListening
                    ? 'bg-red-500/15 text-red-500 hover:bg-red-500/25'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {isListening ? (
                  <span className="relative flex items-center justify-center">
                    <span className="absolute inline-flex h-5 w-5 rounded-full bg-red-500/30 animate-ping" />
                    <Mic className="w-4 h-4 relative" />
                  </span>
                ) : (
                  <Mic className="w-4 h-4" />
                )}
              </Button>
            )}

            {(isStreaming || isTyping) ? (
              <Button
                type="button"
                size="icon"
                onClick={onStop}
                className="h-8 w-8 rounded-full bg-destructive/10 text-destructive hover:bg-destructive/20"
                aria-label="Stop generating"
              >
                <Square className="w-4 h-4 fill-current" />
              </Button>
            ) : (
              <Button
                type="submit"
                size="icon"
                disabled={!inputValue.trim() || isTyping || isStreaming || isAwaitingSereneMind}
                className="h-8 w-8 rounded-full bg-ojas text-primary-foreground hover:bg-ojas-light disabled:opacity-40 disabled:cursor-not-allowed shadow-sm hover:shadow-md transition-all"
                aria-label="Send message"
              >
                <Send className="w-4 h-4" />
              </Button>
            )}
          </div>
        </div>
      </form>

      {isLandingMode && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-[10px] text-center text-muted-foreground/70 mt-3 select-none"
        >
          AI companion &bull; Not a substitute for professional care
        </motion.p>
      )}
    </motion.div>
  );
}
