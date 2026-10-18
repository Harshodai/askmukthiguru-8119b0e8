import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Download, Trash2, Brain } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { CancelFlow } from '@/components/profile/CancelFlow';
import { useToast } from '@/hooks/use-toast';
import { useTranslation } from 'react-i18next';
import { supabase } from '@/integrations/supabase/client';
import { memoryApi } from '@/lib/memoryApi';
import { clearLocalChatData } from '@/lib/chatStorage';
import { clearResponsePreferences } from '@/lib/chat/responsePreferences';
import {
  deleteAllData,
  exportAllData,
  resetProfile,
} from '@/lib/profileStorage';

/**
 * Export + danger zone. Secondary destructive actions sit behind native
 * disclosures so the default view stays calm and scannable.
 */
export const AccountDataCard = () => {
  const { t } = useTranslation();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [cancelOpen, setCancelOpen] = useState(false);
  const [clearLocalOpen, setClearLocalOpen] = useState(false);
  const [eraseMemoriesOpen, setEraseMemoriesOpen] = useState(false);
  const [eraseMemoriesConfirm, setEraseMemoriesConfirm] = useState('');
  const [eraseMemoriesLoading, setEraseMemoriesLoading] = useState(false);

  const handleExport = () => {
    const blob = new Blob([JSON.stringify(exportAllData(), null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `askmukthiguru-export-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast({ title: t('profile.danger.exported', 'Exported'), description: t('profile.danger.exportedDesc', 'Your data was downloaded.') });
  };

  const handleClearLocalData = () => {
    deleteAllData();
    resetProfile();
    clearResponsePreferences();
    toast({
      title: t('profile.danger.localDataCleared', 'Local data cleared'),
      description: t('profile.danger.localDataClearedDesc', 'Device preferences and local history were reset. Your cloud account remains intact.'),
    });
  };

  const handleEraseCloudMemories = async () => {
    if (eraseMemoriesConfirm.trim().toUpperCase() !== 'DELETE') return;
    setEraseMemoriesLoading(true);
    try {
      await memoryApi.deleteAll();
      setEraseMemoriesConfirm('');
      setEraseMemoriesOpen(false);
      toast({
        title: t('profile.danger.cloudMemoriesErased', 'Cloud memories erased'),
        description: t('profile.danger.cloudMemoriesErasedDesc', 'All reflections, second brain notes, and spiritual memories have been permanently deleted.'),
      });
    } catch (e) {
      toast({
        title: t('profile.danger.cloudMemoriesEraseFailed', 'Memory erasure failed'),
        description: e instanceof Error ? e.message : 'unknown',
        variant: 'destructive',
      });
    } finally {
      setEraseMemoriesLoading(false);
    }
  };

  return (
    <Card className="rounded-2xl border border-hairline bg-card shadow-sm">
      <CardHeader className="pb-4">
        <CardTitle className="text-lg font-serif font-semibold text-foreground">{t('profile.danger.accountTitle', 'Account & Data')}</CardTitle>
        <CardDescription>{t('profile.danger.accountSubtitle', 'Export your data, clear local history, or delete your account.')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-2">
          <h4 className="text-[10px] uppercase tracking-[0.14em] font-medium text-muted-foreground">{t('profile.danger.exportData', 'Export data')}</h4>
          <div className="flex flex-col sm:flex-row gap-3">
            <Button variant="outline" className="flex-1 gap-2 rounded-xl min-h-[44px] border-hairline" onClick={handleExport}>
              <Download className="w-4 h-4" /> {t('profile.danger.exportLocalData', 'Export local data')}
            </Button>
            <Button
              variant="outline"
              className="flex-1 gap-2 rounded-xl min-h-[44px] border-hairline"
              onClick={async () => {
                try {
                  const { data: { session } } = await supabase.auth.getSession();
                  if (!session) return toast({ title: t('common.signIn', 'Sign in'), variant: 'destructive' });
                  const { data, error } = await supabase.functions.invoke('export-my-data');
                  if (error) throw error;
                  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `askmukthiguru-cloud-export-${new Date().toISOString().slice(0, 10)}.json`;
                  a.click();
                  URL.revokeObjectURL(url);
                  toast({ title: t('profile.danger.cloudExported', 'Cloud data exported') });
                } catch (e) {
                  toast({ title: t('profile.danger.exportFailed', 'Export failed'), description: e instanceof Error ? e.message : t('common.unknown', 'Unknown error'), variant: 'destructive' });
                }
              }}
            >
              <Download className="w-4 h-4" /> {t('profile.danger.exportCloudData', 'Export cloud data')}
            </Button>
          </div>
        </div>

        <div className="pt-4 border-t border-hairline space-y-3">
          <h4 className="text-[10px] uppercase tracking-[0.14em] font-medium text-destructive/80">{t('profile.danger.zone', 'Danger zone')}</h4>

          <details className="rounded-2xl border border-hairline bg-background/40 px-4 py-3 group">
            <summary className="cursor-pointer text-sm font-medium text-foreground min-h-[32px] flex items-center marker:text-muted-foreground">
              {t('profile.danger.deleteAccountBtn', 'Delete Account')}
            </summary>
            <div className="pt-3 space-y-3">
              <p className="text-xs text-muted-foreground">
                {t('profile.danger.deleteAccountHint', 'A short retention flow runs first — immediate deletion is one of its options.')}
              </p>
              <Dialog open={cancelOpen} onOpenChange={setCancelOpen}>
                <DialogTrigger asChild>
                  <Button variant="destructive" className="gap-2 rounded-xl min-h-[44px]">
                    <Trash2 className="w-4 h-4" /> {t('profile.danger.deleteAccountBtn', 'Delete Account')}
                  </Button>
                </DialogTrigger>
                <DialogContent className="max-w-md rounded-2xl">
                  <DialogHeader>
                    <DialogTitle>{t('cancelFlow.dialogTitle', 'Cancel your account')}</DialogTitle>
                    <DialogDescription>
                      {t('cancelFlow.dialogDescription', 'A short retention flow before we say goodbye.')}
                    </DialogDescription>
                  </DialogHeader>
                  {cancelOpen && (
                    <CancelFlow
                      onComplete={async ({ saved, retention }) => {
                        setCancelOpen(false);
                        if (saved) {
                          toast({ title: t('cancelFlow.offerApplied', 'Offer applied'), description: t('cancelFlow.offerAppliedDesc', 'Your preferences have been kept.') });
                          return;
                        }
                        if (retention === 'delete_immediately') {
                          try {
                            const { error } = await supabase.functions.invoke('delete-my-account', { method: 'POST' });
                            if (error) throw error;
                            await clearLocalChatData();
                            deleteAllData();
                            resetProfile();
                            await supabase.auth.signOut();
                            toast({ title: t('profile.danger.accountDeleted', 'Account deleted') });
                            navigate('/', { replace: true });
                          } catch (e) {
                            toast({ title: t('chat.errorCauseUnknown', 'Something went wrong'), description: e instanceof Error ? e.message : t('common.error', 'Error'), variant: 'destructive' });
                          }
                        } else {
                          try {
                            await supabase.auth.signOut();
                            toast({
                              title: t('profile.danger.deletionScheduled', 'Deletion scheduled'),
                              description: t('profile.danger.deletionScheduledDesc', 'Your account is scheduled for deletion. You can reactivate anytime before the deletion date.'),
                            });
                            navigate('/', { replace: true });
                          } catch (e) {
                            toast({ title: t('chat.errorCauseUnknown', 'Something went wrong'), description: e instanceof Error ? e.message : t('common.error', 'Error'), variant: 'destructive' });
                          }
                        }
                      }}
                      onClose={() => setCancelOpen(false)}
                    />
                  )}
                </DialogContent>
              </Dialog>
            </div>
          </details>

          <details className="rounded-2xl border border-hairline bg-background/40 px-4 py-3 group">
            <summary className="cursor-pointer text-sm font-medium text-foreground min-h-[32px] flex items-center marker:text-muted-foreground">
              {t('profile.danger.clearLocalDataBtn', 'Clear Local Data')}
            </summary>
            <div className="pt-3 space-y-3">
              <p className="text-xs text-muted-foreground">
                {t('profile.danger.clearLocalDataDesc', "Erases this device's cached profile, local chat history, meditation stats, and response preferences. Your account and saved cloud memories remain untouched.")}
              </p>
              <Button variant="outline" className="gap-2 rounded-xl min-h-[44px] border-destructive/30 text-destructive hover:text-destructive" onClick={() => setClearLocalOpen(true)}>
                <Trash2 className="w-4 h-4" /> {t('profile.danger.clearLocalDataBtn', 'Clear Local Data')}
              </Button>
              <AlertDialog open={clearLocalOpen} onOpenChange={setClearLocalOpen}>
                <AlertDialogContent className="rounded-2xl">
                  <AlertDialogHeader>
                    <AlertDialogTitle>{t('profile.danger.clearLocalDataTitle', 'Clear local data on this device?')}</AlertDialogTitle>
                    <AlertDialogDescription>
                      {t('profile.danger.clearLocalDataDesc', "Erases this device's cached profile, local chat history, meditation stats, and response preferences. Your account and saved cloud memories remain untouched.")}
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel className="rounded-xl">{t('common.cancel', 'Cancel')}</AlertDialogCancel>
                    <AlertDialogAction onClick={handleClearLocalData} className="bg-destructive hover:bg-destructive/90 rounded-xl">
                      {t('common.clear', 'Clear')}
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </details>

          <details className="rounded-2xl border border-hairline bg-background/40 px-4 py-3 group">
            <summary className="cursor-pointer text-sm font-medium text-foreground min-h-[32px] flex items-center marker:text-muted-foreground">
              {t('profile.danger.eraseCloudMemoriesBtn', 'Erase Cloud Memories')}
            </summary>
            <div className="pt-3 space-y-3">
              <p className="text-xs text-muted-foreground">
                {t('profile.danger.eraseCloudMemoriesDesc', 'Permanently erases all saved reflections, core memories, second brain notes, and vector knowledge across all your devices. This cannot be undone.')}
              </p>
              <Button variant="outline" className="gap-2 rounded-xl min-h-[44px] border-destructive/30 text-destructive hover:text-destructive" onClick={() => setEraseMemoriesOpen(true)}>
                <Brain className="w-4 h-4" /> {t('profile.danger.eraseCloudMemoriesBtn', 'Erase Cloud Memories')}
              </Button>
              <AlertDialog open={eraseMemoriesOpen} onOpenChange={setEraseMemoriesOpen}>
                <AlertDialogContent className="rounded-2xl">
                  <AlertDialogHeader>
                    <AlertDialogTitle>{t('profile.danger.eraseCloudMemoriesTitle', 'Erase all cloud wisdom & memories?')}</AlertDialogTitle>
                    <AlertDialogDescription>
                      {t('profile.danger.eraseCloudMemoriesDesc', 'Permanently erases all saved reflections, core memories, second brain notes, and vector knowledge across all your devices. This cannot be undone.')}
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <div className="py-2 space-y-1.5">
                    <label htmlFor="erase-cloud-confirm" className="text-xs text-muted-foreground">
                      {t('profile.danger.typeDeleteToConfirm', 'Type DELETE to confirm:')}
                    </label>
                    <Input
                      id="erase-cloud-confirm"
                      value={eraseMemoriesConfirm}
                      onChange={(e) => setEraseMemoriesConfirm(e.target.value)}
                      placeholder="DELETE"
                      className="rounded-xl"
                    />
                  </div>
                  <AlertDialogFooter>
                    <AlertDialogCancel onClick={() => setEraseMemoriesConfirm('')} className="rounded-xl">
                      {t('common.cancel', 'Cancel')}
                    </AlertDialogCancel>
                    <AlertDialogAction
                      onClick={handleEraseCloudMemories}
                      disabled={eraseMemoriesConfirm.trim().toUpperCase() !== 'DELETE' || eraseMemoriesLoading}
                      className="bg-destructive hover:bg-destructive/90 rounded-xl"
                    >
                      {eraseMemoriesLoading ? t('common.erasing', 'Erasing…') : t('common.confirm', 'Confirm')}
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </details>

          <p className="text-[11px] text-muted-foreground pt-1">
            {t('profile.support.debugHint', 'Need help debugging access?')}{' '}
            <Link to="/auth/diagnostics" className="text-ojas hover:underline">
              {t('profile.support.authDiagnostics', 'Open auth diagnostics')}
            </Link>
          </p>
        </div>
      </CardContent>
    </Card>
  );
};
