import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { QUOTA_EVENT, type QuotaInfo } from '@/lib/chat/quotaEvents';

/** UX-011: "N of 5 free questions left today", shown after the first anonymous turn. */
export const QuotaCounter = () => {
  const { t } = useTranslation();
  const [info, setInfo] = useState<QuotaInfo | null>(null);

  useEffect(() => {
    const onQuota = (e: Event) => setInfo((e as CustomEvent<QuotaInfo>).detail);
    window.addEventListener(QUOTA_EVENT, onQuota);
    return () => window.removeEventListener(QUOTA_EVENT, onQuota);
  }, []);

  if (!info) return null;
  return (
    <p className="mx-3 sm:mx-5 mb-2 text-xs text-muted-foreground" role="status" data-testid="quota-counter">
      {t('chat.quotaLeft', {
        defaultValue: '{{remaining}} of {{limit}} free questions left today',
        remaining: info.remaining,
        limit: info.limit,
      })}
    </p>
  );
};

export default QuotaCounter;
