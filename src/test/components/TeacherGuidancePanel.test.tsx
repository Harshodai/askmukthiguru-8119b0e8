import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { TeacherGuidancePanel } from '@/components/chat/TeacherGuidancePanel';

describe('TeacherGuidancePanel', () => {
  it('shows a quiet attribution line and keeps the boundary statement one tap away', () => {
    render(<TeacherGuidancePanel assistantName="Preethaji Guidance" />);

    expect(screen.getByText(/Inspired by the teachings of Sri Preethaji/i)).toBeInTheDocument();
    // The heavy disclaimer is collapsed by default so the first screen stays calm.
    expect(screen.queryByText(/not an impersonation/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /how this guidance works/i }));

    expect(screen.getByText(/not an impersonation/i)).toBeInTheDocument();
    expect(screen.getByText(/professional support/i)).toBeInTheDocument();
  });
});
