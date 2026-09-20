import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';

const MESSAGE_KEYS = [
  { after: 0, key: 'chat.reflecting' },
  { after: 5, key: 'chat.drawingFromTeachings' },
  { after: 15, key: 'chat.contemplating' },
  { after: 30, key: 'chat.answerTakingShape' },
  { after: 55, key: 'chat.stillWorking' },
] as const;

/**
 * Rotating "still thinking" status while a streaming answer hasn't produced
 * any tokens yet. Prevents seekers from thinking the app froze during the
 * 15–45s OpenRouter latency window.
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

  let key = MESSAGE_KEYS[0].key;
  for (const m of MESSAGE_KEYS) if (elapsed >= m.after) key = m.key;
  return t(key);
}
