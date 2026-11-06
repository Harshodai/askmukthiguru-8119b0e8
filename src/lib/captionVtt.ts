/**
 * WebVTT caption for one served clip (NEW-A11Y-4, A11Y-06, WCAG 1.2.2).
 * The cue text is the stored verbatim quote. Nothing is generated, translated
 * or summarised; the only changes are the escaping WebVTT requires and turning
 * blank lines into single line breaks (a blank line ends a cue).
 */
function stamp(totalSeconds: number): string {
  const ms = Math.max(0, Math.round(totalSeconds * 1000));
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  const s = Math.floor((ms % 60_000) / 1000);
  const r = ms % 1000;
  const p = (n: number, w = 2) => String(n).padStart(w, '0');
  return `${p(h)}:${p(m)}:${p(s)}.${p(r, 3)}`;
}

export function buildCaptionVtt(text: string, startSeconds: number, endSeconds: number): string | null {
  const body = text
    .replace(/\r\n?/g, '\n')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .join('\n');
  if (!body || !(endSeconds > startSeconds)) return null;
  return `WEBVTT\n\n${stamp(startSeconds)} --> ${stamp(endSeconds)}\n${body}\n`;
}
