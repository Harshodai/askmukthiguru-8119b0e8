import { describe, it, expect } from 'vitest';
import {
  normalizeForSpeech,
  splitIntoSpeakableSentences,
  SentenceAccumulator,
} from '@/lib/audio/spokenTextNormalizer';

describe('spokenTextNormalizer', () => {
  describe('normalizeForSpeech', () => {
    it('returns empty string for empty input', () => {
      expect(normalizeForSpeech('')).toBe('');
      expect(normalizeForSpeech('   ')).toBe('');
    });

    it('removes markdown headings (#, ##, ###)', () => {
      const input = '### The Awakening of Consciousness\n## Inner Peace\n# Freedom';
      const output = normalizeForSpeech(input);
      expect(output).toBe('The Awakening of Consciousness Inner Peace Freedom');
      expect(output).not.toContain('#');
    });

    it('removes markdown bold, italic, strikethrough, and backticks', () => {
      const input = 'This is **essential wisdom**, *practiced* by seekers with `mindfulness` and ~~fear~~.';
      const output = normalizeForSpeech(input);
      expect(output).toBe('This is essential wisdom, practiced by seekers with mindfulness and fear.');
    });

    it('strips bracketed academic and numeric citations', () => {
      const input = 'Liberation is the dissolution of suffering [1]. See also [2, 3] and [source: Ekam].';
      const output = normalizeForSpeech(input);
      expect(output).toBe('Liberation is the dissolution of suffering. See also and.');
    });

    it('converts markdown links to link text and strips bare URLs', () => {
      const input = 'Visit [Sri Preethaji Teachings](https://ekam.org/teachings) or go to https://ekam.org directly.';
      const output = normalizeForSpeech(input);
      expect(output).toBe('Visit Sri Preethaji Teachings or go to directly.');
    });

    it('removes bullet points and numbered list markers', () => {
      const input = 'Three steps:\n* Be present\n- Observe your thoughts\n+ Connect with the divine\n1. First truth\n2) Second truth';
      const output = normalizeForSpeech(input);
      expect(output).toBe('Three steps: Be present Observe your thoughts Connect with the divine First truth Second truth');
    });

    it('strips thinking/reasoning tags and HTML tags', () => {
      const input = '<think>I should be compassionate and concise</think>Hello seeker. <span class="quote">Grace is here.</span>';
      const output = normalizeForSpeech(input);
      expect(output).toBe('Hello seeker. Grace is here.');
    });

    it('strips emojis that may disrupt TTS speech generation', () => {
      const input = 'Namaste seeker 🙏 Welcome to Ekam ✨ May grace shine on you 🪷';
      const output = normalizeForSpeech(input);
      expect(output).toBe('Namaste seeker Welcome to Ekam May grace shine on you');
    });

    it('normalizes Devanagari danda to periods', () => {
      const input = 'सत्यमेव जयते। नानृतम्॥';
      const output = normalizeForSpeech(input);
      expect(output).toBe('सत्यमेव जयते. नानृतम्.');
    });

    it('collapses multiple spaces, newlines, and repeated punctuation', () => {
      const input = 'Peace is here...\n\n   Do you feel it???   Yes!!';
      const output = normalizeForSpeech(input);
      expect(output).toBe('Peace is here. Do you feel it? Yes!');
    });
  });

  describe('splitIntoSpeakableSentences', () => {
    it('splits text into clean sentences', () => {
      const input = 'The mind is often restless. But in quiet observation, awareness awakens. Do you agree?';
      const sentences = splitIntoSpeakableSentences(input);
      expect(sentences).toEqual([
        'The mind is often restless.',
        'But in quiet observation, awareness awakens.',
        'Do you agree?',
      ]);
    });

    it('does not split on common abbreviations like Dr. or Mr.', () => {
      const input = 'Dr. Sharma visited the ashram yesterday. He spoke about meditation.';
      const sentences = splitIntoSpeakableSentences(input);
      expect(sentences).toEqual([
        'Dr. Sharma visited the ashram yesterday.',
        'He spoke about meditation.',
      ]);
    });

    it('handles Devanagari danda splitting', () => {
      const input = 'शान्ति प्राप्त करें। जीवन सुन्दर है।';
      const sentences = splitIntoSpeakableSentences(input);
      expect(sentences).toEqual([
        'शान्ति प्राप्त करें.',
        'जीवन सुन्दर है.',
      ]);
    });
  });

  describe('SentenceAccumulator', () => {
    it('buffers tokens and yields complete sentences incrementally', () => {
      const accumulator = new SentenceAccumulator(10);

      expect(accumulator.push('Peace begins ')).toEqual([]);
      expect(accumulator.push('within yourself. ')).toEqual(['Peace begins within yourself.']);
      expect(accumulator.push('When you observe without ')).toEqual([]);
      expect(accumulator.push('judgment, clarity emerges! ')).toEqual(['When you observe without judgment, clarity emerges!']);
      expect(accumulator.push('Are you ready?')).toEqual(['Are you ready?']);
      expect(accumulator.flush()).toEqual([]);
    });

    it('flushes any leftover unpunctuated text', () => {
      const accumulator = new SentenceAccumulator(10);
      const first = accumulator.push('First complete thought. ');
      expect(first).toEqual(['First complete thought.']);

      const completed = accumulator.push('And this is the final thought without dot');
      expect(completed).toEqual([]);

      const flushed = accumulator.flush();
      expect(flushed).toEqual(['And this is the final thought without dot']);
    });

    it('strips markdown and citations inside incremental sentences', () => {
      const accumulator = new SentenceAccumulator(10);
      const output = accumulator.push('The **sacred presence** is here [1]. ');
      expect(output).toEqual(['The sacred presence is here.']);
    });

    it('does not split prematurely on abbreviations', () => {
      const accumulator = new SentenceAccumulator(10);
      expect(accumulator.push('We consulted Dr. ')).toEqual([]);
      expect(accumulator.push('Patel for guidance. ')).toEqual(['We consulted Dr. Patel for guidance.']);
    });

    it('does not split prematurely on decimal numbers like 3.14', () => {
      const accumulator = new SentenceAccumulator(10);
      expect(accumulator.push('The factor is 3.')).toEqual([]);
      expect(accumulator.push('14 in this equation. ')).toEqual(['The factor is 3.14 in this equation.']);
    });

    it('splits long run-on sentences on natural clause boundaries to preserve low turnaround latency', () => {
      const accumulator = new SentenceAccumulator(10, 80);
      const chunk1 = 'When you begin your spiritual journey across the hills and valleys of consciousness, ';
      const chunk2 = 'you realize that all life is interconnected and every breath is a gift from the divine.';
      
      const out1 = accumulator.push(chunk1);
      expect(out1.length).toBeGreaterThan(0);
      expect(out1[0]).toContain('When you begin your spiritual journey');

      const out2 = accumulator.push(chunk2);
      expect(out2.length).toBeGreaterThan(0);
      expect(out2[0]).toContain('you realize that all life is interconnected');
    });

    it('resets cleanly', () => {
      const accumulator = new SentenceAccumulator(10);
      accumulator.push('Partial uncommitted');
      accumulator.reset();
      expect(accumulator.flush()).toEqual([]);
    });
  });
});
