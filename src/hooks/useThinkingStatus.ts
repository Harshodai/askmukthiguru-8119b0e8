import { useState, useEffect, useRef } from 'react';

const MESSAGES = [
  { after: 0,  text: 'Guru is reflecting on your question…' },
  { after: 5,  text: 'Connecting to sacred wisdom…' },
  { after: 15, text: 'Contemplating deeply — this may take a moment…' },
  { after: 30, text: 'The answer is taking form…' },
  { after: 55, text: 'Almost ready — deep wisdom takes time…' },
];

/**
 * Rotating "still thinking" status while a streaming answer hasn't produced
 * any tokens yet. Prevents seekers from thinking the app froze during the
 * 15–45s OpenRouter latency window.
 */
export function useThinkingStatus(isStreaming: boolean, hasContent: boolean): string | null {
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

  let msg = MESSAGES[0].text;
  for (const m of MESSAGES) if (elapsed >= m.after) msg = m.text;
  return msg;
}
