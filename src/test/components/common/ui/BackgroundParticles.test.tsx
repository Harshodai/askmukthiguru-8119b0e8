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
});
