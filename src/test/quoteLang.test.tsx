/**
 * NEW-A11Y-5 (A11Y-07, WCAG 3.1.2 Language of Parts): a teacher quote carries
 * lang= only when the clip says which language it is in. Never guessed.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { GuruTeachingCard } from '@/components/chat/ChatMessage';
import { quoteLang } from '@/lib/quoteLang';
import { normalizeCitations, type Citation } from '@/lib/chat/types';

afterEach(() => cleanup());

const citation = (over: Partial<Citation> = {}): Citation => ({
  index: 1,
  url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
  title: 'Clip',
  speaker: 'Sri Krishnaji',
  speakerVerified: true,
  quote: 'Be still, and the truth reveals itself.',
  ...over,
} as Citation);

describe('quoteLang', () => {
  it('accepts well-formed language tags and normalises case', () => {
    expect(quoteLang('hi')).toBe('hi');
    expect(quoteLang('HI')).toBe('hi');
    expect(quoteLang('en-IN')).toBe('en-IN');
    expect(quoteLang('te')).toBe('te');
  });
  it('returns undefined for missing, empty or malformed values', () => {
    expect(quoteLang(undefined)).toBeUndefined();
    expect(quoteLang(null)).toBeUndefined();
    expect(quoteLang('')).toBeUndefined();
    expect(quoteLang('unknown')).toBeUndefined();
    expect(quoteLang('hindi please')).toBeUndefined();
    expect(quoteLang('<script>')).toBeUndefined();
  });
});

describe('GuruTeachingCard quote lang', () => {
  it('marks a Hindi quote lang="hi" even when the UI language is English', () => {
    render(<GuruTeachingCard citation={citation({ language: 'hi', quote: 'शांत रहो' })} verified />);
    expect(screen.getByTestId('guru-teaching-quote')).toHaveAttribute('lang', 'hi');
  });
  it('marks an English quote lang="en"', () => {
    render(<GuruTeachingCard citation={citation({ language: 'en' })} verified />);
    expect(screen.getByTestId('guru-teaching-quote')).toHaveAttribute('lang', 'en');
  });
  it('sets no lang attribute when the clip has no language', () => {
    render(<GuruTeachingCard citation={citation()} verified />);
    expect(screen.getByTestId('guru-teaching-quote')).not.toHaveAttribute('lang');
  });
});

describe('normalizeCitations language', () => {
  const base = { url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', verbatim_text: 'x' };
  it('reads quote_language and ignores the UI-language field', () => {
    const [a] = normalizeCitations([{ ...base, quote_language: 'hi' }]);
    expect(a.language).toBe('hi');
    const [b] = normalizeCitations([{ ...base, language: 'en' }]);
    expect(b.language).toBeUndefined();
    const [c] = normalizeCitations([{ ...base, quote_language: '   ' }]);
    expect(c.language).toBeUndefined();
  });
});
