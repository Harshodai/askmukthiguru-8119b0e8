import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Sparkles, Brain, Trash2, PauseCircle, PlayCircle, ExternalLink, ShieldCheck, AlertTriangle } from 'lucide-react';
import { memoryApi, MemoryApiError } from '@/lib/memoryApi';
import { useToast } from '@/hooks/use-toast';

interface MemorySettingsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  hasConsent: boolean | null;
  onConsentChange: (granted: boolean) => void;
  onMemoriesErased?: () => void;
}

export const MemorySettingsModal: React.FC<MemorySettingsModalProps> = ({
  open,
  onOpenChange,
  hasConsent,
  onConsentChange,
  onMemoriesErased,
}) => {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [toggleLoading, setToggleLoading] = useState(false);
  const [confirmEraseOpen, setConfirmEraseOpen] = useState(false);
  const [erasing, setErasing] = useState(false);

  const isActive = hasConsent === true;

  const handleToggleConsent = async () => {
    setToggleLoading(true);
    const nextState = !isActive;
    try {
      await memoryApi.recordConsent(nextState);
      onConsentChange(nextState);
      if (nextState) {
        toast({
          title: t('chat.memoryBanner.toastEnabledTitle', 'Personal Memory Enabled'),
          description: t(
            'chat.memoryBanner.toastEnabledDesc',
            'Mukthi Guru will now remember key reflections to tailor future guidance.'
          ),
        });
      } else {
        toast({
          title: t('chat.memoryBanner.toastPausedTitle', 'Personal Memory Paused'),
          description: t(
            'chat.memoryBanner.toastPausedDesc',
            'No new reflections will be saved from your conversations.'
          ),
        });
      }
    } catch (err) {
      const msg = err instanceof MemoryApiError ? err.message : 'Could not update memory settings.';
      toast({
        title: t('memory.couldNotSave', 'Could not update setting'),
        description: msg,
        variant: 'destructive',
      });
    } finally {
      setToggleLoading(false);
    }
  };

  const handleEraseAll = async () => {
    setErasing(true);
    try {
      await memoryApi.deleteAll();
      // Record consent as false upon total erasure
      try {
        await memoryApi.recordConsent(false);
        onConsentChange(false);
      } catch {
        // non-critical if consent write fails after data is deleted
      }
      toast({
        title: t('chat.memoryBanner.toastErasedTitle', 'All Memories Erased'),
        description: t(
          'chat.memoryBanner.toastErasedDesc',
          'All personal reflections and wisdom map connections have been deleted.'
        ),
      });
      setConfirmEraseOpen(false);
      onOpenChange(false);
      onMemoriesErased?.();
    } catch (err) {
      const msg = err instanceof MemoryApiError ? err.message : 'Could not erase memories.';
      toast({
        title: t('common.error', 'Error'),
        description: msg,
        variant: 'destructive',
      });
    } finally {
      setErasing(false);
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-md p-6 gap-5" data-testid="memory-settings-modal">
          <DialogHeader className="gap-1.5 text-left">
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-xl bg-ojas/15 text-ojas">
                <Sparkles className="w-5 h-5" />
              </div>
              <div>
                <DialogTitle className="text-base font-serif font-semibold">
                  {t('chat.memorySettings.title', 'Personal Spiritual Memory')}
                </DialogTitle>
                <div className="flex items-center gap-2 mt-0.5">
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${
                      isActive
                        ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                        : 'bg-muted text-muted-foreground border border-border/50'
                    }`}
                  >
                    <span
                      className={`w-1.5 h-1.5 rounded-full ${
                        isActive ? 'bg-emerald-500 animate-pulse' : 'bg-muted-foreground'
                      }`}
                    />
                    {isActive
                      ? t('chat.memorySettings.statusActive', 'Active')
                      : t('chat.memorySettings.statusPaused', 'Paused')}
                  </span>
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <ShieldCheck className="w-3.5 h-3.5 text-ojas" /> Private & Encrypted
                  </span>
                </div>
              </div>
            </div>
            <DialogDescription className="text-xs text-muted-foreground pt-1 leading-relaxed">
              {t(
                'chat.memorySettings.description',
                'Mukthi Guru can remember your reflections, life context, and practices to provide continuous, personalized guidance across sessions.'
              )}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {/* Toggle Recording */}
            <div className="p-3.5 rounded-xl border border-border/60 bg-muted/30 flex items-center justify-between gap-3">
              <div className="space-y-0.5">
                <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                  <Brain className="w-3.5 h-3.5 text-ojas" />
                  {t('chat.memorySettings.recordingLabel', 'Memory Recording')}
                </div>
                <p className="text-[11px] text-muted-foreground leading-normal">
                  {t(
                    'chat.memorySettings.recordingDesc',
                    'When active, reflections from conversations are securely saved to your private wisdom map.'
                  )}
                </p>
              </div>
              <Button
                variant={isActive ? 'outline' : 'default'}
                size="sm"
                onClick={handleToggleConsent}
                disabled={toggleLoading}
                className={`text-xs h-8 px-3 flex-shrink-0 gap-1.5 ${
                  !isActive ? 'bg-ojas hover:bg-ojas-light text-white' : ''
                }`}
                data-testid="toggle-memory-consent-button"
              >
                {isActive ? (
                  <>
                    <PauseCircle className="w-3.5 h-3.5" />
                    {t('chat.memorySettings.pauseAction', 'Pause')}
                  </>
                ) : (
                  <>
                    <PlayCircle className="w-3.5 h-3.5" />
                    {t('chat.memorySettings.resumeAction', 'Resume')}
                  </>
                )}
              </Button>
            </div>

            {/* Profile Deep Link */}
            <div className="flex items-center justify-between text-xs px-1">
              <span className="text-muted-foreground">Want to review individual saved memories?</span>
              <Link
                to="/profile"
                onClick={() => onOpenChange(false)}
                className="text-ojas hover:underline font-medium inline-flex items-center gap-1 text-xs"
              >
                {t('chat.memorySettings.viewAll', 'View in Profile')}
                <ExternalLink className="w-3 h-3" />
              </Link>
            </div>

            {/* Danger Zone: Erase All Memories */}
            <div className="pt-3 border-t border-destructive/20 space-y-2">
              <div className="text-xs font-semibold text-destructive flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5" />
                {t('chat.memorySettings.eraseTitle', 'Erase All Memories')}
              </div>
              <p className="text-[11px] text-muted-foreground">
                {t(
                  'chat.memorySettings.eraseDesc',
                  'Permanently delete all reflections, core notes, and personal wisdom map connections. This action cannot be undone.'
                )}
              </p>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => setConfirmEraseOpen(true)}
                className="w-full text-xs h-8 gap-1.5 mt-1"
                data-testid="erase-all-memories-button"
              >
                <Trash2 className="w-3.5 h-3.5" />
                {t('chat.memorySettings.eraseButton', 'Erase Everything')}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Confirmation Dialog for Permanent Erasure */}
      <AlertDialog open={confirmEraseOpen} onOpenChange={setConfirmEraseOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="text-destructive flex items-center gap-2">
              <AlertTriangle className="w-5 h-5" />
              {t('chat.memorySettings.eraseConfirmTitle', 'Are you absolutely sure?')}
            </AlertDialogTitle>
            <AlertDialogDescription className="text-xs text-muted-foreground leading-relaxed">
              {t(
                'chat.memorySettings.eraseConfirmDesc',
                'This will permanently erase all saved reflections, core facts, and connections in your personal wisdom map across all servers.'
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={erasing}>
              {t('common.cancel', 'Cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => void handleEraseAll()}
              disabled={erasing}
              className="bg-destructive hover:bg-destructive/90 text-white gap-1.5"
              data-testid="confirm-erase-all-button"
            >
              {erasing ? (
                t('chat.memorySettings.erasing', 'Erasing memories…')
              ) : (
                <>
                  <Trash2 className="w-4 h-4" />
                  {t('chat.memorySettings.eraseConfirmButton', 'Yes, erase all memories')}
                </>
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
};
