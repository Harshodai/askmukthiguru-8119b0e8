import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { BackgroundParticles } from '@/components/common/ui/BackgroundParticles';

describe('BackgroundParticles', () => {
  it('renders the requested number of particles', () => {
    const { container } = render(<BackgroundParticles count={5} />);
    const particles = container.querySelectorAll('.rounded-full');
    expect(particles.length).toBe(5);
  });

  it('applies custom container className', () => {
    const { container } = render(<BackgroundParticles count={0} className="custom-bg" />);
    expect(container.firstChild).toHaveClass('custom-bg');
  });

  it('caps the default (no count prop) particle count at 24, not 40', () => {
    // Regression: 40 particles x double blurred box-shadow was reproducibly
    // hanging the renderer / causing full-page blackouts on scroll at
    // ordinary desktop widths, not just <=768px mobile. See the comment in
    // BackgroundParticles.tsx for the full history.
    const { container } = render(<BackgroundParticles />);
    const particles = container.querySelectorAll('.rounded-full');
    expect(particles.length).toBe(24);
  });
});
