import { useTranslation } from 'react-i18next';
import { useState } from "react";
import { Check, ChevronDown, Lock, Sparkles, Heart, Users } from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAssistants } from "@/hooks/useAssistants";
import { supabase } from "@/integrations/supabase/client";
import { toast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

const ICONS: Record<string, typeof Sparkles> = {
  general: Sparkles,
  relationship: Heart,
  sky: Lock,
};

interface AssistantSwitcherProps {
  variant?: 'default' | 'chip';
}

export function AssistantSwitcher({ variant = 'default' }: AssistantSwitcherProps) {
  const { t } = useTranslation();
  const { assistants, selected, setSelectedSlug } = useAssistants();
  const [open, setOpen] = useState(false);
  const [inviteCode, setInviteCode] = useState("");
  const [redeeming, setRedeeming] = useState(false);

  if (!selected) return null;

  const SelectedIcon = ICONS[selected.slug] ?? Users;

  const handleRedeem = async () => {
    const code = inviteCode.trim();
    if (!code) return;
    setRedeeming(true);
    try {
      const { data: a } = await supabase
        .from("assistants")
        .select("id, slug, name")
        .eq("invite_code", code)
        .maybeSingle();
      if (!a) {
        toast({ title: t('chat.invalidInviteCode'), variant: "destructive" });
        return;
      }
      const { data: session } = await supabase.auth.getSession();
      const uid = session.session?.user.id;
      if (!uid) {
        toast({ title: t('chat.signInToRedeem'), variant: "destructive" });
        return;
      }
      const { error } = await supabase
        .from("assistant_access")
        .insert({ user_id: uid, assistant_id: a.id, granted_via: "invite" });
      if (error && !String(error.message).includes("duplicate")) {
        toast({ title: t('chat.couldNotRedeem'), description: error.message, variant: "destructive" });
        return;
      }
      toast({ title: t('chat.unlockedAssistant', { name: a.name }), description: t('chat.switchToIt') });
      setInviteCode("");
      setTimeout(() => window.location.reload(), 600);
    } finally {
      setRedeeming(false);
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          className={
            variant === 'chip'
              ? "inline-flex items-center gap-1 rounded-full border border-ojas/20 bg-ojas/5 hover:bg-ojas/10 transition-colors px-2 py-0.5 text-[11px] text-foreground/80"
              : "inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/30 hover:bg-muted/60 transition-colors px-2.5 py-1 text-[11px] text-foreground/80 max-w-[180px]"
          }
          title={t('chat.switchAssistant')}
        >
          <SelectedIcon className="w-3 h-3 text-primary shrink-0" />
          <span className="font-medium truncate">{selected.name}</span>
          <ChevronDown className="w-3 h-3 text-muted-foreground shrink-0" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 p-2">
        <p className="text-[11px] uppercase tracking-wider text-muted-foreground px-2 pt-1 pb-2">
          {t('chat.assistants')}
        </p>
        <div className="space-y-1">
          {assistants.map((a) => {
            const Icon = ICONS[a.slug] ?? Users;
            const active = a.slug === selected.slug;
            return (
              <button
                key={a.id}
                onClick={() => {
                  setSelectedSlug(a.slug);
                  setOpen(false);
                }}
                className={cn(
                  "w-full flex items-start gap-2 rounded-md px-2 py-2 text-left hover:bg-muted/60 transition-colors",
                  active && "bg-primary/10",
                )}
              >
                <Icon className="w-4 h-4 mt-0.5 text-primary shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium truncate">{a.name}</span>
                    {a.visibility !== "public" && (
                      <Badge variant="outline" className="text-[9px] px-1 py-0">
                        {a.visibility}
                      </Badge>
                    )}
                  </div>
                  <p className="text-[11px] text-muted-foreground line-clamp-2">
                    {a.description}
                  </p>
                </div>
                {active && <Check className="w-3.5 h-3.5 text-primary mt-1 shrink-0" />}
              </button>
            );
          })}
        </div>
        <div className="border-t border-border mt-2 pt-2 px-1 space-y-1.5">
          <p className="text-[11px] text-muted-foreground">
            {t('chat.haveInviteCode')}
          </p>
          <div className="flex gap-1.5">
            <Input
              placeholder={t('chat.inviteCodePlaceholder')}
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value)}
              className="h-8 text-xs"
            />
            <Button size="sm" onClick={handleRedeem} disabled={redeeming || !inviteCode.trim()}>
              {redeeming ? "…" : t('common.redeem')}
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
