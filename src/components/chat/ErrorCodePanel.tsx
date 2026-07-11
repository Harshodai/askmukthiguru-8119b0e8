import { useTranslation } from 'react-i18next';
import { Copy, ExternalLink } from 'lucide-react';
import { useState } from 'react';
import type { ChatBusError } from '@/lib/chatErrorBus';

interface ErrorCodePanelProps {
  error: ChatBusError;
  compact?: boolean;
}

export const ErrorCodePanel = ({ error, compact = false }: ErrorCodePanelProps) => {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const CAUSE_BY_KIND: Record<string, string> = {
    unauthorized: t('chat.errorCauseUnauthorized'),
    rate_limited: t('chat.errorCauseRateLimited'),
    server_error: t('chat.errorCauseServerError'),
    network: t('chat.errorCauseNetwork'),
    timeout: t('chat.errorCauseTimeout'),
    unknown: t('chat.errorCauseUnknown'),
  };

  const copyTrace = () => {
    const payload = [
      `Code: ${error.code}`,
      `Kind: ${error.kind}`,
      `Title: ${error.title}`,
      `Time: ${new Date(error.at).toISOString()}`,
      error.messageId ? `MessageId: ${error.messageId}` : null,
      error.detail ? `Detail: ${error.detail}` : null,
    ]
      .filter(Boolean)
      .join('\n');
    void navigator.clipboard?.writeText(payload).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <div
      className={`rounded-lg border border-destructive/25 bg-destructive/5 text-foreground/90 ${
        compact ? 'px-3 py-2 text-[12px]' : 'px-3.5 py-3 text-[13px]'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[11px] font-semibold text-destructive tracking-wide">
          {error.code}
        </span>
        <button
          type="button"
          onClick={copyTrace}
          className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
          aria-label={t('chat.copyTraceAria')}
        >
          <Copy className="w-3 h-3" />
          {copied ? t('common.copied') : t('chat.copyTrace')}
        </button>
      </div>
      <p className="mt-1.5 font-semibold text-destructive leading-tight">{error.title}</p>
      <dl className="mt-2 grid grid-cols-[72px_1fr] gap-y-1 gap-x-2 text-[12px] leading-relaxed">
        <dt className="text-muted-foreground">{t('chat.cause')}</dt>
        <dd className="text-foreground/85">{CAUSE_BY_KIND[error.kind] ?? CAUSE_BY_KIND.unknown}</dd>
        <dt className="text-muted-foreground">{t('chat.nextStep')}</dt>
        <dd className="text-foreground/85">{error.nextStep}</dd>
      </dl>
      {error.detail && (
        <details className="mt-2">
          <summary className="text-[11px] text-muted-foreground cursor-pointer hover:text-foreground/70 select-none inline-flex items-center gap-1">
            <ExternalLink className="w-3 h-3" /> {t('chat.technicalDetail')}
          </summary>
          <pre className="mt-1 text-[11px] text-muted-foreground whitespace-pre-wrap break-all font-mono bg-background/40 rounded px-2 py-1.5 border border-border/40">
            {error.detail}
          </pre>
        </details>
      )}
    </div>
  );
};
