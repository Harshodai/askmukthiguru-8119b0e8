import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FamiliarityProgressWheel } from '@/components/profile/FamiliarityProgressWheel';

describe('FamiliarityProgressWheel', () => {
  it('presents the selected guidance depth without claiming spiritual mastery', () => {
    render(<FamiliarityProgressWheel level="practitioner" />);

    expect(screen.getByLabelText('Guidance depth: 66%')).toBeInTheDocument();
    expect(screen.getByText(/guidance preference, not a claim of spiritual mastery/i)).toBeInTheDocument();
    expect(screen.queryByText(/mastered core spiritual concepts/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/internalized/i)).not.toBeInTheDocument();
  });
});
