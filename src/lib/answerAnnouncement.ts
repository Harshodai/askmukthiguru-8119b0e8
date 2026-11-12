/**
 * One polite screen-reader announcement per arrived answer (NEW-A11Y-6,
 * A11Y-13, WCAG 4.1.3). It never reads the answer or the quote: the seeker
 * moves to the message and reads it at their own pace. Errors are skipped
 * because the error card already renders role="alert".
 */
import { useEffect, useRef, useState } from 'react';
import type { Message } from '@/lib/chatStorage';

const ZERO_WIDTH = String.fromCharCode(0x200b);

export const ANSWER_ARRIVED_TEXT = 'Mukthi Guru has replied. The answer is below.';
export const ANSWER_ABSTAINED_TEXT =
  'Mukthi Guru found no close match in the recorded teachings for this question.';

export function describeArrival(message: Message): string | null {
  if (message.role !== 'guru' || message.isWelcome || message.error) return null;
  return message.groundingState === 'abstained' ? ANSWER_ABSTAINED_TEXT : ANSWER_ARRIVED_TEXT;
}

/**
 * @param busy true while a request or stream is in flight; nothing is announced
 *             until it ends, so a streamed answer is announced once, not per token.
 */
export function useAnswerAnnouncement(messages: Message[], busy: boolean): string {
  const lastAnnouncedId = useRef<string | null>(messages[messages.length - 1]?.id ?? null);
  const flip = useRef(false);
  const [text, setText] = useState('');

  const last = messages[messages.length - 1];
  useEffect(() => {
    if (busy || !last || last.id === lastAnnouncedId.current) return;
    lastAnnouncedId.current = last.id;
    const next = describeArrival(last);
    if (!next) return;
    // Identical text is not re-read by screen readers; alternate an invisible
    // character so two abstains in a row are both announced.
    flip.current = !flip.current;
    setText(flip.current ? next : `${next}${ZERO_WIDTH}`);
  }, [busy, last]);

  return text;
}
