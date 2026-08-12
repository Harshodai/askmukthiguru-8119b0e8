import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { GuidancePreview } from './GuidancePreview';

describe('GuidancePreview', () => {
  it('explains the selected tone, depth, and source-aware response boundary', () => {
    render(<GuidancePreview guruTone="gentle" familiarityLevel="beginner" />);

    expect(screen.getByTestId('guidance-preview')).toHaveTextContent(
      'Warm, steady guidance that makes room for your experience before offering a next step.',
    );
    expect(screen.getByTestId('guidance-preview')).toHaveTextContent(
      'It explains spiritual terms plainly before building on them.',
    );
    expect(screen.getByTestId('guidance-preview')).toHaveTextContent(
      'Source-aware by design',
    );
  });
});
