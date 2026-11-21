/**
 * Spoken Text Normalizer for Speech-to-Text and Text-to-Speech Pipelining.
 *
 * Prepares raw text (often containing markdown, citations, URLs, code blocks,
 * and visual formatting from LLM completions) for natural, fluid vocalization.
 */

// Common titles and abbreviations that should not trigger sentence boundaries
const ABBREVIATIONS = new Set([
  'mr', 'mrs', 'ms', 'dr', 'prof', 'sr', 'jr',
  'vs', 'etc', 'eg', 'ie', 'approx', 'dept',
  'st', 'no', 'vol', 'jan', 'feb', 'mar', 'apr',
  'jun', 'jul', 'aug', 'sep', 'sept', 'oct', 'nov', 'dec'
]);

/**
 * Strips markdown, bracketed citations, URLs, HTML tags, and visual formatting
 * into clean, natural text suitable for TTS engines.
 */
export function normalizeForSpeech(text: string): string {
  if (!text) return '';

  let cleaned = text;

  // 1. Remove thinking / internal reasoning blocks if present (e.g. <think>...</think>)
  cleaned = cleaned.replace(/<think[\s\S]*?<\/think>/gi, '');
  cleaned = cleaned.replace(/<thinking[\s\S]*?<\/thinking>/gi, '');

  // 2. Remove code blocks entirely (```...```) or replace with spoken transition
  cleaned = cleaned.replace(/```[\s\S]*?```/g, '');

  // 3. Remove HTML tags
  cleaned = cleaned.replace(/<[^>]+>/g, '');

  // 4. Remove bracketed citations (e.g., [1], [2, 3], [1-4], [citation needed], [source: ...])
  cleaned = cleaned.replace(/\[\s*(?:\d+[\d\s,\-–]*|citation|source[^\]]*|reference[^\]]*)\]/gi, '');

  // 5. Convert markdown links [text](url) to just the text
  cleaned = cleaned.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');

  // 6. Remove bare URLs (e.g. https://... or http://...)
  cleaned = cleaned.replace(/https?:\/\/\S+/gi, '');

  // 7. Remove markdown headings (#, ##, ###, etc.)
  cleaned = cleaned.replace(/^#{1,6}\s+/gm, '');

  // 8. Convert bullet list items to comma/period separated text
  // Match lines starting with *, -, +, or bullet unicode
  cleaned = cleaned.replace(/^[\s]*[-*+•]\s+/gm, '');

  // 9. Remove numbered list prefixes at start of line (e.g., "1. ", "2) ")
  cleaned = cleaned.replace(/^[\s]*\d+[.)]\s+/gm, '');

  // 10. Remove blockquote markers ("> ")
  cleaned = cleaned.replace(/^>\s*/gm, '');

  // 11. Remove bold, italic, strikethrough, and inline code formatting
  // Bold/italic: ***text***, **text**, *text*, ___text___, __text__, _text_
  cleaned = cleaned.replace(/[*_]{1,3}([^*_]+)[*_]{1,3}/g, '$1');
  // Strikethrough: ~~text~~
  cleaned = cleaned.replace(/~~([^~]+)~~/g, '$1');
  // Inline code: `text`
  cleaned = cleaned.replace(/`([^`]+)`/g, '$1');

  // 12. Normalize Devanagari danda '।' and double danda '॥' to periods
  cleaned = cleaned.replace(/[।॥]/g, '. ');

  // 13. Remove decorative emojis that produce awkward speech synthesizer outputs
  cleaned = cleaned.replace(/\p{Extended_Pictographic}/gu, '');

  // 14. Fix space before punctuation (e.g., from citation removal "word [1]." -> "word .")
  cleaned = cleaned.replace(/\s+([,.;:!?])/g, '$1');

  // 15. Normalize ellipses (...) or multiple periods to a single period
  cleaned = cleaned.replace(/\.{2,}/g, '.');

  // 16. Normalize repeated exclamation/question marks
  cleaned = cleaned.replace(/!{2,}/g, '!');
  cleaned = cleaned.replace(/\?{2,}/g, '?');

  // 17. Collapse multiple spaces and newlines
  cleaned = cleaned.replace(/[\r\n]+/g, ' ');
  cleaned = cleaned.replace(/\s{2,}/g, ' ');

  return cleaned.trim();
}

/**
 * Splits normalized text into distinct sentences suitable for TTS chunks.
 * Handles Indian danda, English sentence terminators, and skips abbreviation periods.
 */
export function splitIntoSpeakableSentences(text: string): string[] {
  const normalized = normalizeForSpeech(text);
  if (!normalized) return [];

  // Match sentence terminators (. ! ?) followed by whitespace or end of string
  const rawParts = normalized.split(/(?<=[.!?])\s+/);
  const result: string[] = [];

  let currentBuffer = '';

  for (let i = 0; i < rawParts.length; i++) {
    const part = rawParts[i].trim();
    if (!part) continue;

    if (currentBuffer) {
      currentBuffer += ' ' + part;
    } else {
      currentBuffer = part;
    }

    // Check if the current buffer ends with an abbreviation like "Dr." or "Mr."
    const lastWordMatch = currentBuffer.match(/([a-zA-Z]+)\.$/);
    if (lastWordMatch) {
      const word = lastWordMatch[1].toLowerCase();
      if (ABBREVIATIONS.has(word) && i < rawParts.length - 1) {
        // Don't split; continue accumulating into currentBuffer
        continue;
      }
    }

    // Check if ends with a digit followed by dot (e.g. "3.") and next starts with digit
    if (/\d\.$/.test(currentBuffer) && i < rawParts.length - 1 && /^\d/.test(rawParts[i + 1])) {
      continue;
    }

    result.push(currentBuffer);
    currentBuffer = '';
  }

  if (currentBuffer.trim()) {
    result.push(currentBuffer.trim());
  }

  return result.filter((s) => s.length > 0);
}

/**
 * SentenceAccumulator: Incremental token-to-sentence pipeline.
 *
 * Buffers streaming LLM token deltas and yields completed sentences
 * immediately as punctuation boundaries are encountered.
 */
export class SentenceAccumulator {
  private buffer = '';
  private minSentenceLength = 15; // Minimum characters before treating a punctuation as a sentence break
  private maxClauseLength = 120; // Maximum characters before looking for clause breaks in run-on sentences

  constructor(minSentenceLength = 15, maxClauseLength = 120) {
    this.minSentenceLength = minSentenceLength;
    this.maxClauseLength = maxClauseLength;
  }

  /**
   * Pushes a token or text chunk into the accumulator.
   * Returns an array of newly completed, normalized sentences.
   */
  public push(chunk: string): string[] {
    this.buffer += chunk;
    const completed: string[] = [];

    let searchStart = 0;
    while (searchStart < this.buffer.length) {
      const remainingBuffer = this.buffer.slice(searchStart);
      
      // 1. Primary check: Sentence terminators (. ! ? । \n)
      const match = remainingBuffer.match(/([.!?।\n])(\s+|$)/);
      if (match && match.index !== undefined) {
        const boundaryIndex = searchStart + match.index + match[1].length;
        const candidate = this.buffer.slice(0, boundaryIndex).trim();
        const remainder = this.buffer.slice(boundaryIndex);

        // Check if ends with a decimal number like "3." where next is digit or buffer ends mid-token
        if (match[1] === '.' && /\d\.$/.test(candidate) && (remainder.length === 0 || /^\d/.test(remainder))) {
          searchStart = boundaryIndex;
          continue;
        }

        // Check for abbreviation (e.g., "Dr.")
        const lastWordMatch = candidate.match(/([a-zA-Z]+)\.$/);
        if (lastWordMatch && ABBREVIATIONS.has(lastWordMatch[1].toLowerCase())) {
          searchStart = boundaryIndex;
          continue;
        }

        // Check if candidate is too short to be a standalone sentence and there's more text
        if (candidate.length < this.minSentenceLength && remainder.trim().length > 0) {
          searchStart = boundaryIndex;
          continue;
        }

        // Valid sentence boundary found
        const normalized = normalizeForSpeech(candidate);
        if (normalized) {
          completed.push(normalized);
        }

        this.buffer = remainder.replace(/^\s+/, '');
        searchStart = 0;
        continue;
      }

      // 2. Secondary check: Handle run-on sentences without terminators
      // If buffer exceeds maxClauseLength, split on clause boundaries (, ; : — or whitespace)
      if (this.buffer.length >= this.maxClauseLength) {
        const clauseMatch = this.buffer.slice(searchStart).match(/([,;:—–]|\s{2,})\s+/);
        if (clauseMatch && clauseMatch.index !== undefined && searchStart + clauseMatch.index >= this.minSentenceLength) {
          const boundaryIndex = searchStart + clauseMatch.index + clauseMatch[1].length;
          const candidate = this.buffer.slice(0, boundaryIndex).trim();
          const remainder = this.buffer.slice(boundaryIndex);

          const normalized = normalizeForSpeech(candidate);
          if (normalized) {
            completed.push(normalized);
          }

          this.buffer = remainder.replace(/^\s+/, '');
          searchStart = 0;
          continue;
        } else if (this.buffer.length >= this.maxClauseLength * 1.5) {
          // If no clause boundary found and buffer is very large, split at the last space
          const lastSpaceIndex = this.buffer.lastIndexOf(' ');
          if (lastSpaceIndex > this.minSentenceLength) {
            const candidate = this.buffer.slice(0, lastSpaceIndex).trim();
            const remainder = this.buffer.slice(lastSpaceIndex + 1);

            const normalized = normalizeForSpeech(candidate);
            if (normalized) {
              completed.push(normalized);
            }

            this.buffer = remainder.replace(/^\s+/, '');
            searchStart = 0;
            continue;
          }
        }
      }

      break;
    }

    return completed;
  }

  /**
   * Flushes any remaining uncommitted text in the buffer when the stream ends.
   */
  public flush(): string[] {
    const remaining = this.buffer.trim();
    this.buffer = '';
    if (!remaining) return [];

    const normalized = normalizeForSpeech(remaining);
    return normalized ? [normalized] : [];
  }

  /**
   * Clears the internal buffer without emitting.
   */
  public reset(): void {
    this.buffer = '';
  }
}
