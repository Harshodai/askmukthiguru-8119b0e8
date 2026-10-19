import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';

/**
 * Detect a YouTube embed that will never play: embedding disabled by the owner
 * (YouTube error 101/150), blocked by network / offline, blocked by an
 * extension, or blocked by our own CSP.
 *
 * An `<iframe>` gives the host page no error signal — a refused embed renders a
 * document that is visually indistinguishable from a playing one, which is why
 * both playback surfaces used to sit on a black box labelled "Playing …". Two
 * independent signals are therefore required:
 *
 *   1. YouTube's `onError` postMessage handshake (the contract `LazyYouTube` in
 *      `ChatMessage.tsx` already relies on).
 *   2. A bounded "no sign of life" timer. When the frame is blocked outright the
 *      handshake never arrives *because nothing ever loaded*, so a message-only
 *      listener would wait forever and the dead black box would stay.
 *
 * The timer is cleared by real evidence of life — a postMessage from the YouTube
 * origin, checked against this hook's own iframe — never by the frame's `load`
 * event: a refused frame fires `load` for the error document too. Because `load`
 * no longer counts, `onFrameLoad` sends the IFrame API `listening` handshake so a
 * healthy player starts posting its `onReady`/`onStateChange` liveness events.
 * `EMBED_LOAD_TIMEOUT_MS` is deliberately generous: on an abnormally slow link it
 * could mark a healthy embed unavailable, and the honest failure mode for that
 * false positive is a notice plus a working "Watch on YouTube" link, never a dead
 * box claiming to play. Callers must render that escape hatch.
 */

const EMBED_LOAD_TIMEOUT_MS = 10_000;

/** YouTube emits 101/150 for "embedding disabled by request"; 2/5/100 are
 *  bad-parameter / HTML5-player / deleted-video — all unplayable in an embed. */
const UNPLAYABLE_EMBED_CODES = new Set([2, 5, 100, 101, 150]);

export const useYouTubeEmbedError = (
  videoId: string | null | undefined,
  active: boolean,
): { embedError: boolean; iframeRef: RefObject<HTMLIFrameElement>; onFrameLoad: () => void } => {
  const [embedError, setEmbedError] = useState(false);
  const timerRef = useRef<number | null>(null);
  const aliveRef = useRef(false);
  // Owned here so `handleMessage` can prove a postMessage came from OUR frame, not
  // some other frame on the page. Consumers attach it to the `<iframe ref=…>`.
  // Plain `useRef<HTMLIFrameElement>(null)` (not the `| null` union) so the type is
  // exactly the `RefObject<HTMLIFrameElement>` the `ref` prop accepts.
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    if (!active || !videoId) {
      setEmbedError(false);
      return;
    }

    aliveRef.current = false;
    const stillAlive = () => {
      aliveRef.current = true;
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };

    const handleMessage = (event: MessageEvent) => {
      if (event.origin !== 'https://www.youtube.com') return;
      // Only accept messages posted by OUR iframe. A real cross-frame message always
      // carries a non-null source, so a mismatched source is another frame's traffic;
      // a source-less synthetic dispatch is still let through.
      if (event.source && iframeRef.current?.contentWindow !== event.source) return;
      let data: unknown;
      try {
        data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
      } catch {
        return; // not a YouTube control message
      }
      const payload = data as { event?: unknown; info?: unknown; data?: unknown } | null;
      if (!payload || typeof payload.event !== 'string') return;

      if (payload.event === 'onError' && UNPLAYABLE_EMBED_CODES.has(Number(payload.info ?? payload.data))) {
        stillAlive(); // stop the timer; the verdict is already in
        setEmbedError(true);
        return;
      }
      // Any other recognised event (onReady/onStateChange/infoDelivery) proves
      // the player is alive; a later onError still flips the state.
      stillAlive();
    };

    window.addEventListener('message', handleMessage);
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null;
      if (!aliveRef.current) setEmbedError(true);
    }, EMBED_LOAD_TIMEOUT_MS);

    return () => {
      window.removeEventListener('message', handleMessage);
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [active, videoId]);

  /** Attach to the iframe's `onLoad`. A refused frame never fires it either — so
   *  `load` is NOT treated as liveness. Instead ask the player to start posting. */
  const onFrameLoad = useCallback(() => {
    const frameWindow = iframeRef.current?.contentWindow;
    if (!frameWindow) return;
    try {
      frameWindow.postMessage(
        JSON.stringify({
          event: 'listening',
          id: iframeRef.current?.id ?? '',
          channel: 'widget',
        }),
        'https://www.youtube.com',
      );
    } catch {
      // postMessage can throw on a torn-down window; the timeout stays armed.
    }
  }, []);

  return { embedError, iframeRef, onFrameLoad };
};
