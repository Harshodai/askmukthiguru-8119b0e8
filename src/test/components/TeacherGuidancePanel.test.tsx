import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TeacherGuidancePanel } from '@/components/chat/TeacherGuidancePanel';

describe('TeacherGuidancePanel', () => {
  it('states attribution boundaries and offers priority languages', () => {
    const onLanguageChange = vi.fn();
    render(
      <TeacherGuidancePanel
        assistantName="Preethaji Guidance"
        language="en"
        onLanguageChange={onLanguageChange}
      />,
    );

    expect(screen.getByText(/Inspired by the teachings of Sri Preethaji/i)).toBeInTheDocument();
    expect(screen.getByText(/not an impersonation/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'తెలుగు' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Hinglish' }));
    expect(onLanguageChange).toHaveBeenCalledWith('hinglish');
  });
});
