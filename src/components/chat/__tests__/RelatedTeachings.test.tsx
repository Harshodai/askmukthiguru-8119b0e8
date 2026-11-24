import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RelatedTeachings } from '../RelatedTeachings';
import { normalizeRelatedClips } from '@/lib/chat/types';

const QUOTE = 'Suffering is not a punishment; it is a call to awaken.';
const wire = [
  {
    url: 'https://www.youtube.com/watch?v=abcdefghijk&t=42s',
    text_snippet: QUOTE,
    speaker: null,
    attribution: 'unverified clip',
    speaker_verified: false,
    timestamp_seconds: 42,
    is_answer: false,
  },
];

describe('RelatedTeachings', () => {
  it('renders heading, attribution label and the verbatim quote', () => {
    render(<RelatedTeachings clips={normalizeRelatedClips(wire)} />);
    expect(screen.getByText('Related teachings, not a direct answer')).toBeTruthy();
    expect(screen.getAllByText('unverified clip').length).toBeGreaterThan(0);
    expect(screen.getByText(QUOTE)).toBeTruthy();
  });

  it('renders nothing when absent or empty', () => {
    const { container, rerender } = render(<RelatedTeachings />);
    expect(container.innerHTML).toBe('');
    rerender(<RelatedTeachings clips={[]} />);
    expect(container.innerHTML).toBe('');
    expect(normalizeRelatedClips(undefined)).toEqual([]);
  });
});
