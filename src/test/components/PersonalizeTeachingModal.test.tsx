import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { PersonalizeTeachingModal } from '@/components/chat/PersonalizeTeachingModal';

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('PersonalizeTeachingModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders auth_required mode with sign in CTA and benefits', () => {
    const onOpenChange = vi.fn();
    render(
      <BrowserRouter>
        <PersonalizeTeachingModal
          open={true}
          onOpenChange={onOpenChange}
          mode="auth_required"
        />
      </BrowserRouter>
    );

    expect(screen.getByText('Tune This Wisdom to Your Life')).toBeDefined();
    expect(screen.getByText("Sign in to connect Sri Bhagavan and Sri Amma's teachings with your personal reflections and life journey.")).toBeDefined();
    expect(screen.getByText('Tailored reflections on what teachings mean for your unique challenges.')).toBeDefined();
    expect(screen.getByText('Sign In or Sign Up')).toBeDefined();
  });

  it('navigates to /auth?redirect=/chat on primary CTA in auth_required mode', () => {
    const onOpenChange = vi.fn();
    render(
      <BrowserRouter>
        <PersonalizeTeachingModal
          open={true}
          onOpenChange={onOpenChange}
          mode="auth_required"
        />
      </BrowserRouter>
    );

    const ctaButton = screen.getByText('Sign In or Sign Up');
    fireEvent.click(ctaButton);

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(mockNavigate).toHaveBeenCalledWith('/auth?redirect=/chat');
  });

  it('renders memory_empty mode with Second Brain guidance and CTA', () => {
    const onOpenChange = vi.fn();
    render(
      <BrowserRouter>
        <PersonalizeTeachingModal
          open={true}
          onOpenChange={onOpenChange}
          mode="memory_empty"
        />
      </BrowserRouter>
    );

    expect(screen.getByText('Make This Teaching Yours')).toBeDefined();
    expect(screen.getByText("Personalization tailors teachings using reflections and insights you save in your Second Brain. You haven't saved any reflections yet.")).toBeDefined();
    expect(screen.getByText('Go to Second Brain')).toBeDefined();
  });

  it('navigates to /profile?tab=memory on primary CTA in memory_empty mode', () => {
    const onOpenChange = vi.fn();
    render(
      <BrowserRouter>
        <PersonalizeTeachingModal
          open={true}
          onOpenChange={onOpenChange}
          mode="memory_empty"
        />
      </BrowserRouter>
    );

    const ctaButton = screen.getByText('Go to Second Brain');
    fireEvent.click(ctaButton);

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(mockNavigate).toHaveBeenCalledWith('/profile?tab=memory');
  });

  it('closes modal when clicking Maybe later', () => {
    const onOpenChange = vi.fn();
    render(
      <BrowserRouter>
        <PersonalizeTeachingModal
          open={true}
          onOpenChange={onOpenChange}
          mode="auth_required"
        />
      </BrowserRouter>
    );

    const maybeLater = screen.getByText('Maybe later');
    fireEvent.click(maybeLater);

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
