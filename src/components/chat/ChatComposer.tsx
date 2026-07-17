import { useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import { useToast } from '@/hooks/use-toast';
import {
  Send, Square, Flame, Sparkles, Plus, Mic, Volume2, X, FileText,
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
import { type PipelineStep } from './ThinkingPills';
import { SlashCommandMenu, type SlashCommandId } from './SlashCommandMenu';
import type { PromptInputMessage } from '@/components/ai-elements/prompt-input';
import {
  PromptInput,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
} from '@/components/ai-elements/prompt-input';

interface ChatComposerProps {
  inputValue: string;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  attachedFiles: { id: string; name: string; content: string }[];
  onAddFile: (file: { name: string; content: string }) => void;
  onRemoveFile: (id: string) => void;
  onInputChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onPaste?: (e: React.ClipboardEvent<HTMLTextAreaElement>) => void;
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
  attachedFiles,
  onAddFile,
  onRemoveFile,
  onInputChange,
  onPaste,
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
  const { t } = useTranslation();
  const { toast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const MAX_ATTACHMENT_BYTES = 2 * 1024 * 1024; // 2 MB cap for chat text files

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > MAX_ATTACHMENT_BYTES) {
      toast?.({
        title: t('chat.attachmentTooLarge') === 'chat.attachmentTooLarge' ? 'Attachment too large' : t('chat.attachmentTooLarge'),
        description: t('chat.attachmentSizeHint') === 'chat.attachmentSizeHint' ? 'Please choose a text file under 2 MB.' : t('chat.attachmentSizeHint'),
        variant: 'destructive',
      });
      e.target.value = '';
      return;
    }

    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      if (content) {
        onAddFile({ name: file.name, content });
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  const showThinking =
    showInstantPill || showPipeline || isTyping || (isStreaming && inputValue === '');

  const handleFormSubmit = (_message: PromptInputMessage, e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    onSubmit(e);
  };

  return (
    <motion.div

      className="w-full max-w-3xl mx-auto"
    >
      <div className="flex items-center justify-start gap-2 mb-2 px-1">
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

      <PromptInput
        onSubmit={handleFormSubmit}
        role="form"
        aria-label={t('chat.messageComposer')}
        className={`rounded-[var(--radius-card)] border bg-card/95 backdrop-blur-xl transition-all duration-300 overflow-visible ${
          inputFocused || isListening
            ? 'border-ojas/40 shadow-lg shadow-ojas/[0.06]'
            : 'border-hairline shadow-sm'
        }`}
      >
        {isAwaitingSereneMind && (
          <div className="flex items-center justify-between px-5 pt-4 pb-2 border-b border-border/40 bg-ojas/5 rounded-t-3xl">
            <span className="text-xs text-ojas font-medium">
              {t('chat.sereneMindRequired')}
            </span>
            <button
              type="button"
              onClick={onSereneMind}
              className="px-3 py-1 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground text-xs font-semibold hover:shadow-md transition-all"
            >
              {t('chat.openSereneMind')}
            </button>
          </div>
        )}

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

        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          accept=".txt"
          className="hidden"
        />

        {attachedFiles && attachedFiles.length > 0 && (
          <div className="flex flex-wrap gap-2 px-5 pt-2 pb-1">
            {attachedFiles.map((file) => (
              <div
                key={file.id}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-zinc-900 border border-zinc-800 text-[11px] text-zinc-300 select-none"
              >
                <span className="font-medium text-emerald-400 font-mono truncate max-w-[120px]">
                  {file.name}
                </span>
                <span className="text-[9px] text-muted-foreground font-mono">
                  ({Math.round(file.content.length / 102.4) / 10} KB)
                </span>
                <button
                  type="button"
                  onClick={() => onRemoveFile(file.id)}
                  aria-label={`Remove file ${file.name}`}
                  className="p-0.5 rounded-full hover:bg-zinc-850 text-muted-foreground hover:text-zinc-200 transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        <PromptInputTextarea
          ref={inputRef as React.Ref<HTMLTextAreaElement>}
          data-tour="chat-input"
          value={inputValue}
          onChange={onInputChange}
          onPaste={onPaste}
          onKeyDown={onKeyDown}
          onFocus={onFocus}
          onBlur={onBlur}
          placeholder={
            isAwaitingSereneMind
              ? t('chat.inputPlaceholderSereneMind')
              : isListening
                ? t('chat.inputPlaceholderListening')
                : t('chat.inputPlaceholder')
          }
          rows={1}
          aria-label={t('chat.yourMessage') === 'chat.yourMessage' ? 'Your message' : t('chat.yourMessage')}
          className="min-h-9 max-h-80 w-full bg-transparent border-none outline-none resize-none px-4 pt-4 pb-1 text-foreground placeholder:text-muted-foreground/60 text-[15px] leading-relaxed scrollbar-spiritual disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ minHeight: '28px' }}
          disabled={isAwaitingSereneMind}
        />

        <PromptInputFooter className="flex items-center gap-1.5 px-3 pb-3 pt-2">
          <PromptInputTools>
            <AssistantSwitcher variant="chip" />

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 rounded-full text-muted-foreground hover:text-foreground"
                  aria-label={t('chat.moreActions')}
                >
                  <Plus className="w-4 h-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" side="top" className="w-48">
                <DropdownMenuItem onClick={onSereneMind}>
                  <Flame className="w-4 h-4 mr-2 text-ojas" />
                  {t('chat.sereneMind')}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={onGuidedMeditation}>
                  <Sparkles className="w-4 h-4 mr-2 text-ojas" />
                  {t('chat.guidedMeditation')}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => fileInputRef.current?.click()}>
                  <FileText className="w-4 h-4 mr-2 text-ojas" />
                  {t('chat.attachTextFile') === 'chat.attachTextFile' ? 'Attach Text File' : t('chat.attachTextFile')}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </PromptInputTools>

          <div className="flex-1" />

          <PromptInputTools>
            {(
              <Button
                data-testid="start-voice-input-button"
                type="button"
                size="icon-sm"
                variant="ghost"
                onClick={onVoiceToggle}
                aria-label={isListening ? t('chat.stopRecording') : t('chat.startVoiceInput')}
                aria-pressed={isListening}
                title={isListening ? t('chat.stopRecording') : t('chat.startVoiceInput')}
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
              <PromptInputSubmit
                type="button"
                size="icon-sm"
                onClick={onStop}
                className="h-8 w-8 rounded-full bg-destructive/10 text-destructive hover:bg-destructive/20"
                aria-label={t('chat.stop')}
                status="streaming"
              >
                <Square className="w-4 h-4 fill-current" />
              </PromptInputSubmit>
            ) : (
              <PromptInputSubmit
                type="submit"
                size="icon-sm"
                disabled={!inputValue.trim() || isTyping || isStreaming || isAwaitingSereneMind}
                className="h-8 w-8 rounded-full bg-ojas text-primary-foreground hover:bg-ojas-light disabled:opacity-40 disabled:cursor-not-allowed shadow-sm hover:shadow-md transition-all"
                aria-label={t('chat.send') === 'chat.send' ? 'Send message' : t('chat.send')}
              >
                <Send className="w-4 h-4" />
              </PromptInputSubmit>
            )}
          </PromptInputTools>
        </PromptInputFooter>
      </PromptInput>

      {isLandingMode && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-[10px] text-center text-muted-foreground/70 mt-3 select-none"
        >
          {t('chat.aiCompanionNotice')}
        </motion.p>
      )}
    </motion.div>
  );
}
