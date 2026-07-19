import { useEffect, useState } from "react";
import { Brain, Lock, Plus, Trash2, Download, ShieldAlert, Loader2 } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import { useRequireAuth } from "@/hooks/useRequireAuth";
import { BrandedSpinner } from "@/components/common/BrandedSpinner";
import {
  secondBrainApi,
  deriveBrainUnlock,
  type BrainItem,
  SecondBrainApiError,
} from "@/lib/secondBrainApi";

const KIND_OPTIONS: BrainItem["kind"][] = [
  "reflection",
  "entity",
  "preference",
  "relationship",
  "journal",
];

export default function SecondBrainPage() {
  const { t } = useTranslation();
  const { loading: authLoading } = useRequireAuth();
  const { toast } = useToast();

  const [wrapMode, setWrapMode] = useState<"server_wrapped" | "session_unlock" | null>(null);
  const [passphrase, setPassphrase] = useState(""); // Mode-B only; never persisted
  const [unlocked, setUnlocked] = useState(false);
  const [items, setItems] = useState<BrainItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [newKind, setNewKind] = useState<BrainItem["kind"]>("reflection");
  const [newText, setNewText] = useState("");
  const [adding, setAdding] = useState(false);
  const [showEnablePrivate, setShowEnablePrivate] = useState(false);
  const [showShredConfirm, setShowShredConfirm] = useState(false);
  const [enablePassphrase, setEnablePassphrase] = useState("");
  const [enablePassphraseConfirm, setEnablePassphraseConfirm] = useState("");
  const [brainUnlockKey, setBrainUnlockKey] = useState<string | undefined>(undefined);

  const loadItems = async (unlock?: string) => {
    setLoading(true);
    try {
      const list = await secondBrainApi.listItems(unlock);
      setItems(list);
      setUnlocked(true);
    } catch (err) {
      if (err instanceof SecondBrainApiError && err.status === 403) {
        setUnlocked(false); // Mode-B, wrong or missing passphrase
      } else {
        toast({
          title: t('brain.loadError', "Couldn't load your reflections"),
          description: err instanceof Error ? err.message : String(err),
          variant: "destructive",
        });
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (authLoading) return;
    (async () => {
      try {
        const status = await secondBrainApi.provision();
        setWrapMode(status.wrap_mode);
        if (status.wrap_mode === "server_wrapped") {
          await loadItems();
        } else {
          setLoading(false); // Mode-B: wait for the user to enter their passphrase
        }
      } catch (err) {
        setLoading(false);
        toast({
          title: t('brain.unavailable', "Reflections unavailable"),
          description: err instanceof Error ? err.message : String(err),
          variant: "destructive",
        });
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading]);

  const handleUnlock = async () => {
    if (!passphrase.trim()) return;
    const derived = await deriveBrainUnlock(passphrase);
    setBrainUnlockKey(derived);
    await loadItems(derived);
  };

  const handleAdd = async () => {
    if (!newText.trim()) return;
    setAdding(true);
    try {
      await secondBrainApi.addItem(newKind, newText.trim(), brainUnlockKey);
      setNewText("");
      await loadItems(brainUnlockKey);
      toast({ title: t('brain.saved', "Saved to your reflections") });
    } catch (err) {
      toast({
        title: t('brain.couldNotSave', "Couldn't save"),
        description: err instanceof Error ? err.message : String(err),
        variant: "destructive",
      });
    } finally {
      setAdding(false);
    }
  };

  const handleForget = async (id: string) => {
    try {
      await secondBrainApi.forgetItem(id);
      setItems((prev) => prev.filter((i) => i.id !== id));
    } catch (err) {
      toast({
        title: t('brain.couldNotDelete', "Couldn't delete"),
        description: err instanceof Error ? err.message : String(err),
        variant: "destructive",
      });
    }
  };

  const handleExport = async () => {
    try {
      const data = await secondBrainApi.exportBrain(brainUnlockKey);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "my-reflections-export.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast({
        title: t('brain.exportFailed', "Export failed"),
        description: err instanceof Error ? err.message : String(err),
        variant: "destructive",
      });
    }
  };

  const handleEnablePrivateMode = async () => {
    if (enablePassphrase.length < 8) {
      toast({ title: t('brain.passphraseMinLength', "Passphrase must be at least 8 characters"), variant: "destructive" });
      return;
    }
    if (enablePassphrase !== enablePassphraseConfirm) {
      toast({ title: t('brain.passphrasesDontMatch', "Passphrases don't match"), variant: "destructive" });
      return;
    }
    try {
      await secondBrainApi.enableSessionUnlock(enablePassphrase);
      const derived = await deriveBrainUnlock(enablePassphrase);
      setBrainUnlockKey(derived);
      setWrapMode("session_unlock");
      setPassphrase(enablePassphrase);
      setShowEnablePrivate(false);
      setEnablePassphrase("");
      setEnablePassphraseConfirm("");
      toast({ title: t('brain.privateModeEnabled', "Private Mode enabled — even we can't read your reflections now.") });
      await loadItems(derived);
    } catch (err) {
      toast({
        title: t('brain.couldNotEnablePrivate', "Couldn't enable Private Mode"),
        description: err instanceof Error ? err.message : String(err),
        variant: "destructive",
      });
    }
  };

  const handleShred = async () => {
    try {
      await secondBrainApi.shred();
      setShowShredConfirm(false);
      setItems([]);
      setUnlocked(false);
      setBrainUnlockKey(undefined);
      const status = await secondBrainApi.provision();
      setWrapMode(status.wrap_mode);
      if (status.wrap_mode === "server_wrapped") {
        await loadItems();
      } else {
        setLoading(false);
      }
      toast({ title: t('brain.permanentlyDeleted', "Reflections permanently deleted.") });
    } catch (err) {
      toast({
        title: t('brain.couldNotDeleteVault', "Couldn't delete vault"),
        description: err instanceof Error ? err.message : String(err),
        variant: "destructive",
      });
    }
  };

  const handleCloseEnablePrivate = () => {
    setShowEnablePrivate(false);
    setEnablePassphrase("");
    setEnablePassphraseConfirm("");
  };

  if (authLoading) {
    return <BrandedSpinner />;
  }

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex items-center justify-between mb-2">
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Brain className="w-6 h-6 text-ojas" />
            {t('brain.title', "My Reflections")}
          </h1>
          {wrapMode === "session_unlock" && (
            <Badge variant="outline" className="gap-1">
              <Lock className="w-3 h-3" /> {t('brain.privateMode', "Private Mode")}
            </Badge>
          )}
        </div>
        <p className="text-sm text-muted-foreground mb-6">
          {t('brain.subtitle', "A private, encrypted log of your reflections, insights, and preferences — used to personalize your guidance.")}
        </p>

        {wrapMode === "session_unlock" && !unlocked && !loading && (
          <Card className="p-6 mb-6">
            <p className="text-sm text-muted-foreground mb-3">
              {t('brain.privateModeIntro', "Private Mode is on — enter your passphrase to unlock your reflections for this session. It's never sent anywhere except this one request, and never stored.")}
            </p>
            <div className="flex gap-2">
              <Input
                type="password"
                placeholder={t('brain.passphrasePlaceholder', "Your passphrase")}
                value={passphrase}
                onChange={(e) => setPassphrase(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleUnlock()}
              />
              <Button onClick={handleUnlock} disabled={!passphrase.trim()}>
                {t('brain.unlockButton', "Unlock")}
              </Button>
            </div>
          </Card>
        )}

        {loading && (
          <div className="flex justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        )}

        {!loading && unlocked && (
          <>
            <Card className="p-4 mb-6">
              <div className="flex gap-2 mb-2">
                <select
                  className="rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={newKind}
                  onChange={(e) => setNewKind(e.target.value as BrainItem["kind"])}
                >
                  {KIND_OPTIONS.map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
              </div>
              <Textarea
                placeholder={t('brain.addPlaceholder', "Something worth remembering — a reflection, a goal, a preference...")}
                value={newText}
                onChange={(e) => setNewText(e.target.value)}
                maxLength={8000}
                rows={3}
              />
              <div className="flex justify-end mt-2">
                <Button onClick={handleAdd} disabled={adding || !newText.trim()}>
                  <Plus className="w-4 h-4 mr-1" /> {t('brain.addButton', "Add")}
                </Button>
              </div>
            </Card>

            <div className="space-y-3 mb-6">
              {items.length === 0 && (
                <p className="text-sm text-muted-foreground text-center py-8">
                  {t('brain.emptyState', "Nothing here yet — your reflections will appear as you use the app, or you can add one above.")}
                </p>
              )}
              {items.map((item) => (
                <Card key={item.id} className="p-4 flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <Badge variant="secondary" className="mb-1 capitalize">
                      {item.kind}
                    </Badge>
                    <p className="text-sm text-foreground break-words">{item.text}</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {new Date(item.created_at * 1000).toLocaleDateString()}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleForget(item.id)}
                    title={t('brain.forgetTooltip', "Forget this")}
                  >
                    <Trash2 className="w-4 h-4 text-muted-foreground" />
                  </Button>
                </Card>
              ))}
            </div>

            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={handleExport}>
                <Download className="w-4 h-4 mr-1" /> {t('brain.exportButton', "Export")}
              </Button>
              {wrapMode !== "session_unlock" && (
                <Button variant="outline" onClick={() => setShowEnablePrivate(true)}>
                  <Lock className="w-4 h-4 mr-1" /> {t('brain.enablePrivateMode', "Enable Private Mode")}
                </Button>
              )}
              <Button
                variant="outline"
                className="text-destructive hover:text-destructive"
                onClick={() => setShowShredConfirm(true)}
              >
                <ShieldAlert className="w-4 h-4 mr-1" /> {t('brain.deleteEverything', "Delete Everything")}
              </Button>
            </div>
          </>
        )}
      </div>

      <Dialog open={showEnablePrivate} onOpenChange={(open) => !open && handleCloseEnablePrivate()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('brain.enablePrivateTitle', "Enable Private Mode")}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {t('brain.enablePrivateWarning', "Once enabled, your reflections are encrypted with a key derived from this passphrase. We will never see it, and if you forget it, your reflections cannot be recovered by anyone, including us. This is by design.")}
          </p>
          <Input
            type="password"
            placeholder={t('brain.passphraseChoose', "Choose a passphrase (min. 8 characters)")}
            value={enablePassphrase}
            onChange={(e) => setEnablePassphrase(e.target.value)}
          />
          <Input
            type="password"
            placeholder={t('brain.passphraseConfirm', "Confirm passphrase")}
            value={enablePassphraseConfirm}
            onChange={(e) => setEnablePassphraseConfirm(e.target.value)}
          />
          <DialogFooter>
            <Button variant="outline" onClick={handleCloseEnablePrivate}>
              {t('brain.cancel', "Cancel")}
            </Button>
            <Button onClick={handleEnablePrivateMode}>{t('brain.enablePrivateMode', "Enable Private Mode")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={showShredConfirm} onOpenChange={setShowShredConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('brain.deleteTitle', "Delete all reflections?")}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {t('brain.deleteWarning', "This permanently destroys the encryption key for every item in your reflections. This cannot be undone by anyone.")}
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowShredConfirm(false)}>
              {t('brain.cancel', "Cancel")}
            </Button>
            <Button variant="destructive" onClick={handleShred}>
              {t('brain.deleteEverything', "Delete Everything")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppShell>
  );
}
