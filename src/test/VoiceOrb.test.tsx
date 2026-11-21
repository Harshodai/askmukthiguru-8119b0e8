import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { VoiceOrb } from '@/components/chat/VoiceOrb';

describe('VoiceOrb', () => {
  it('renders correctly in idle state', () => {
    render(<VoiceOrb state="idle" />);
    const container = screen.getByTestId('voice-orb-container');
    expect(container).toBeDefined();
    expect(screen.getByText('Paused')).toBeDefined();
    expect(container.getAttribute('aria-label')).toBe('Voice mode orb: idle');
  });

  it('renders correctly in listening state with audio level', () => {
    render(<VoiceOrb state="listening" audioLevel={0.7} />);
    expect(screen.getByText('Listening')).toBeDefined();
    const container = screen.getByTestId('voice-orb-container');
    expect(container.getAttribute('aria-label')).toBe('Voice mode orb: listening');
  });

  it('renders correctly in thinking/reflecting state', () => {
    render(<VoiceOrb state="thinking" />);
    expect(screen.getByText('Reflecting')).toBeDefined();
    const container = screen.getByTestId('voice-orb-container');
    expect(container.getAttribute('aria-label')).toBe('Voice mode orb: thinking');
  });

  it('renders correctly in speaking state with animated equalizer bars', () => {
    render(<VoiceOrb state="speaking" />);
    expect(screen.getByText('Speaking')).toBeDefined();
    const container = screen.getByTestId('voice-orb-container');
    expect(container.getAttribute('aria-label')).toBe('Voice mode orb: speaking');
  });

  it('fires onClick when clicked', () => {
    const handleClick = vi.fn();
    render(<VoiceOrb state="idle" onClick={handleClick} />);
    const container = screen.getByTestId('voice-orb-container');
    fireEvent.click(container);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });
});
