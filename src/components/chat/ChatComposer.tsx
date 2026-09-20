import { memo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  CHAT_MAX_SINGLE_ATTACHMENT_BYTES,
  formatMegabytes,
} from '@/lib/chat/attachmentLimits';
import { motion, AnimatePresence } from 'framer-motion';
import { useToast } from '@/hooks/use-toast';
import {
  Send, Square, Flame, Sparkles, Plus, Mic, X, FileText, CornerDownLeft, AudioLines,
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

import { hapticAudio } from '@/lib/audio/hapticAudio';

interface ChatComposerProps {
  inputValue: string;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  attachedFiles: { id: string; name: string; content: string }[];
  onAddFile: (file: File | { name: string; content: string }) => void | Promise<boolean>;
  onRemoveFile: (id: string) => void;
  onInputChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onPaste?: (e: React.ClipboardEvent<HTMLTextAreaElement>) => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  onSubmit: (e?: React.FormEvent) => void;
  onStop: () => void;
  isTyping: boolean;
  isStreaming: boolean;
  isAwaitingSereneMind: boolean;
  isQuotaExceeded?: boolean;
  isListening: boolean;
  isHandsFreeVoice: boolean;
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
  onHandsFreeVoiceToggle: () => void;
  onTtsToggle: () => void;
  onLanguageChange: (code: string) => void;
  capabilities?: {
    sereneMind: boolean;
    guidedMeditation: boolean;
    textAttachments: boolean;
    documentAttachments?: boolean;
    imageAttachments?: boolean;
    audioAttachments?: boolean;
    videoAttachments?: boolean;
    ocr?: boolean;
    voiceInput: boolean;
  };
  onSereneMind: () => void;
  onGuidedMeditation: () => void;
  onFocus: () => void;
  onBlur: () => void;
  onSlashCommand: (cmd: SlashCommandId) => void;
}

function ChatComposerInner({
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
  isQuotaExceeded,
  isListening,
  isHandsFreeVoice,
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
  onHandsFreeVoiceToggle,
  onTtsToggle,
  onLanguageChange,
  capabilities,
  onSereneMind,
  onGuidedMeditation,
  onFocus,
  onBlur,
  onSlashCommand,
}: ChatComposerProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);

  const actionCapabilities = capabilities ?? {
    sereneMind: true,
    guidedMeditation: true,
    textAttachments: true,
    documentAttachments: true,
    imageAttachments: true,
    audioAttachments: true,
    videoAttachments: true,
    ocr: true,
    voiceInput: true,
  };
  const attachmentCapabilities = {
    text: actionCapabilities.textAttachments,
    documents: actionCapabilities.documentAttachments ?? actionCapabilities.textAttachments,
    images: actionCapabilities.imageAttachments ?? actionCapabilities.textAttachments,
    audio: actionCapabilities.audioAttachments ?? actionCapabilities.textAttachments,
    video: actionCapabilities.videoAttachments ?? actionCapabilities.textAttachments,
  };
  const attachmentsAvailable = Object.values(attachmentCapabilities).some(Boolean);
  const hasMoreActions = actionCapabilities.sereneMind || actionCapabilities.guidedMeditation || attachmentsAvailable || actionCapabilities.voiceInput;
  const attachmentAccept = [
    ...(attachmentCapabilities.text ? ['.txt', '.md', '.markdown', '.csv', '.tsv', '.json', '.log', '.xml', '.html', '.htm', '.yaml', '.yml'] : []),
    ...(attachmentCapabilities.documents ? ['.pdf', '.docx', '.pptx', '.xlsx'] : []),
    ...(attachmentCapabilities.images ? ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'] : []),
    ...(attachmentCapabilities.audio ? ['.mp3', '.wav', '.m4a', '.ogg', '.flac'] : []),
    ...(attachmentCapabilities.video ? ['.webm', '.mp4', '.mov', '.avi', '.mkv'] : []),
  ].join(',');

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > CHAT_MAX_SINGLE_ATTACHMENT_BYTES) {
      toast?.({
        title: t('chat.attachmentTooLarge') === 'chat.attachmentTooLarge' ? 'Attachment too large' : t('chat.attachmentTooLarge'),
        description: t('chat.attachmentSizeHint') === 'chat.attachmentSizeHint' ? `Please choose a file under ${formatMegabytes(CHAT_MAX_SINGLE_ATTACHMENT_BYTES)}.` : t('chat.attachmentSizeHint'),
        variant: 'destructive',
      });
      e.target.value = '';
      return;
    }

    setIsUploading(true);
    try {
      await onAddFile(file);
    } catch (error) {
      toast?.({
        title: 'Attachment processing failed',
        description: error instanceof Error ? error.message : 'Please try another file.',
        variant: 'destructive',
      });
    } finally {
      setIsUploading(false);
      e.target.value = '';
    }
  };

  const showThinking =
    showInstantPill || showPipeline || isTyping || (isStreaming && inputValue === '');

  const handleFormSubmit = (_message: PromptInputMessage, e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!(isTyping || isStreaming)) hapticAudio.playDispatchChime();
    onSubmit(e);
  };

  return (
    <motion.div
      className="w-full max-w-3xl mx-auto py-2 sm:py-3"
    >
      <PromptInput
        onSubmit={handleFormSubmit}
        role="form"
        aria-label={t('chat.messageComposer')}
        className={`rounded-2xl border border-hairline bg-card transition-colors duration-200 overflow-visible ${
          inputFocused || isListening
            ? 'border-ojas/50 shadow-md'
            : 'shadow-sm'
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
          accept={attachmentAccept}
          className="hidden"
        />

        {attachedFiles && attachedFiles.length > 0 && (
          <div className="flex flex-wrap gap-2 px-5 pt-2 pb-1" dir="auto">
            {attachedFiles.map((file) => (
              <div
                key={file.id}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-muted/40 border border-border/60 text-[11px] text-foreground/80 select-none"
              >
                <span className="font-medium text-ojas font-mono truncate max-w-[120px]">
                  {file.name}
                </span>
                <span className="text-[9px] text-muted-foreground font-mono">
                  ({Math.round(file.content.length / 102.4) / 10} KB)
                </span>
                <button
                  type="button"
                  onClick={() => onRemoveFile(file.id)}
                  aria-label={`Remove file ${file.name}`}
                  className="p-0.5 rounded-full hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
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
            isQuotaExceeded
              ? t('chat.quotaExceededPlaceholder') === 'chat.quotaExceededPlaceholder'
                ? 'Sign in to continue'
                : t('chat.quotaExceededPlaceholder')
              : isAwaitingSereneMind
                ? t('chat.inputPlaceholderSereneMind')
                : isListening
                  ? t('chat.inputPlaceholderListening')
                  : t('chat.inputPlaceholder')
          }
          rows={1}
          dir={currentLanguage === 'ur' ? 'rtl' : 'auto'}
          enterKeyHint="send"
          aria-label={t('chat.yourMessage') === 'chat.yourMessage' ? 'Your message' : t('chat.yourMessage')}
          className="min-h-9 max-h-[120px] w-full bg-transparent border-none outline-none resize-none px-4 pt-4 pb-1 text-foreground placeholder:text-muted-foreground/60 text-[15px] leading-relaxed scrollbar-spiritual focus:ring-1 focus:ring-ojas/30 disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ minHeight: '28px' }}
          disabled={isAwaitingSereneMind || isQuotaExceeded}
        />

        {isHandsFreeVoice && (
          <div className="mx-3 mb-1.5 flex items-center justify-between gap-3 rounded-xl border border-ojas/25 bg-ojas/5 px-3 py-2 text-xs">
            <div className="flex min-w-0 items-center gap-2 text-foreground">
              <AudioLines className="w-3.5 h-3.5 text-ojas shrink-0" />
              <span className="truncate">{t('chat.voiceConversationOn', 'Voice conversation is on — speak naturally; the Guru will answer aloud.')}</span>
            </div>
            <button
              type="button"
              onClick={onHandsFreeVoiceToggle}
              className="shrink-0 rounded-lg px-2 py-1 text-[11px] font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              {t('chat.stop', 'Stop')}
            </button>
          </div>
        )}

        <PromptInputFooter className="flex items-center gap-1.5 px-3 pb-3 pt-2">
          <PromptInputTools>
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
            <AssistantSwitcher variant="chip" />

            {hasMoreActions && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="min-h-[44px] min-w-[44px] sm:h-8 sm:w-8 rounded-full text-muted-foreground hover:text-foreground flex items-center justify-center"
                    aria-label={t('chat.moreActions')}
                  >
                    <Plus className="w-4 h-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" side="top" className="w-48">
                  {actionCapabilities.sereneMind && (
                    <DropdownMenuItem onClick={onSereneMind}>
                      <Flame className="w-4 h-4 mr-2 text-ojas" />
                      {t('chat.sereneMind')}
                    </DropdownMenuItem>
                  )}
                  {actionCapabilities.guidedMeditation && (
                    <DropdownMenuItem onClick={onGuidedMeditation}>
                      <Sparkles className="w-4 h-4 mr-2 text-ojas" />
                      {t('chat.guidedMeditation')}
                    </DropdownMenuItem>
                  )}
                  {attachmentsAvailable && (
                    <DropdownMenuItem disabled={isUploading} onClick={() => fileInputRef.current?.click()}>
                      <FileText className="w-4 h-4 mr-2 text-ojas" />
                      {isUploading ? t('chat.processingAttachment', 'Processing attachment…') : t('chat.attachMedia', 'Attach media or document')}
                    </DropdownMenuItem>
                  )}
                  {actionCapabilities.voiceInput && (
                    <DropdownMenuItem onClick={onHandsFreeVoiceToggle}>
                      <AudioLines className="w-4 h-4 mr-2 text-ojas" />
                      {isHandsFreeVoice ? t('chat.turnOffVoiceConversation', 'Turn off voice conversation') : t('chat.voiceConversation', 'Voice conversation')}
                    </DropdownMenuItem>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </PromptInputTools>

          <div className="flex-1" />

          <PromptInputTools>
            {actionCapabilities.voiceInput && (
              <Button
                data-testid="start-voice-input-button"
                type="button"
                size="icon-sm"
                variant="ghost"
                onClick={onVoiceToggle}
                aria-label={isListening ? t('chat.stopRecording') : t('chat.startVoiceInput')}
                aria-pressed={isListening}
                title={isListening ? t('chat.stopRecording') : t('chat.startVoiceInput')}
                className={`min-h-[44px] min-w-[44px] sm:h-9 sm:w-9 rounded-full transition-all flex items-center justify-center ${
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
              <div className="flex items-center gap-1.5">
                <PromptInputSubmit
                  type="button"
                  size="icon-sm"
                  onClick={onStop}
                  className="min-h-[44px] min-w-[44px] sm:h-8 sm:w-8 rounded-full bg-destructive/10 text-destructive hover:bg-destructive/20 flex items-center justify-center"
                  aria-label={t('chat.stop')}
                  title={t('chat.stopGenerating', 'Stop generating')}
                >
                  <Square className="w-3.5 h-3.5 fill-current" />
                </PromptInputSubmit>

                {inputValue.trim() && (
                  <PromptInputSubmit
                    type="submit"
                    size="icon-sm"
                    className="min-h-[44px] sm:h-9 px-3 rounded-xl bg-saffron-gold text-zinc-950 hover:bg-amber-400 font-semibold text-xs shadow-md transition-all flex items-center gap-1.5"
                    aria-label={t('chat.queueMessage', 'Queue message')}
                    title={t('chat.queueMessage', 'Queue follow-up message')}
                  >
                    <CornerDownLeft className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">{t('chat.queueFollowUp', 'Queue')}</span>
                  </PromptInputSubmit>
                )}
              </div>
            ) : (
              <PromptInputSubmit
                type="submit"
                size="icon-sm"
                disabled={!inputValue.trim() || isAwaitingSereneMind || isQuotaExceeded || isUploading}
                className="min-h-[44px] min-w-[44px] sm:h-9 sm:w-9 rounded-xl bg-ojas text-white hover:bg-ojas-dark disabled:opacity-40 disabled:cursor-not-allowed shadow-sm hover:shadow-md transition-all flex items-center justify-center"
                aria-label={t('chat.send') === 'chat.send' ? 'Send message' : t('chat.send')}
              >
                <Send className="w-4 h-4" />
              </PromptInputSubmit>
            )}
          </PromptInputTools>
        </PromptInputFooter>
      </PromptInput>

      {isLandingMode && (
        <div className="mt-1.5 flex items-center justify-center gap-1.5 text-[10px] text-muted-foreground select-none">
          <span className="hidden sm:inline">{t('chat.keyboardHint', 'Enter to send · Shift+Enter for a new line')}</span>
          <span className="sm:hidden">{t('chat.aiCompanionNotice')}</span>
        </div>
      )}
    </motion.div>
  );
}

ChatComposerInner.displayName = 'ChatComposer';

export const ChatComposer = memo(ChatComposerInner);
