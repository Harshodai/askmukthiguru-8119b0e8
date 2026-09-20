import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';

const STATUS_KEYS = [
  { after: 0, key: 'chat.thinking.rotatingReflecting' },
  { after: 5, key: 'chat.thinking.rotatingConnecting' },
  { after: 15, key: 'chat.contemplating' },
  { after: 30, key: 'chat.answerTakingShape' },
  { after: 55, key: 'chat.thinking.rotatingAlmostReady' },
] as const;

/**
 * Rotating localized "still thinking" status while a streaming answer hasn't produced
 * any tokens yet. This is deliberately presentation-only: it never exposes model reasoning.
 */
export function useThinkingStatus(isStreaming: boolean, hasContent: boolean): string | null {
  const { t } = useTranslation();
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef<number | null>(null);

  useEffect(() => {
    if (!isStreaming || hasContent) {
      setElapsed(0);
      startRef.current = null;
      return;
    }
    startRef.current = Date.now();
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - (startRef.current ?? Date.now())) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, [isStreaming, hasContent]);

  if (!isStreaming || hasContent) return null;

  let statusKey: (typeof STATUS_KEYS)[number]['key'] = STATUS_KEYS[0].key;
  for (const item of STATUS_KEYS) if (elapsed >= item.after) statusKey = item.key;
  return t(statusKey);
}
