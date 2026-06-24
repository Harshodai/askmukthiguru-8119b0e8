import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FloatingActionButton } from '@/components/common/ui/FloatingActionButton';

describe('FloatingActionButton', () => {
  it('renders when visible and hides when not visible', () => {
    const { rerender } = render(
      <FloatingActionButton visible={false} onClick={vi.fn()} label="Jump" />,
    );
    expect(screen.queryByRole('button')).not.toBeInTheDocument();

    rerender(<FloatingActionButton visible={true} onClick={vi.fn()} label="Jump" />);
    expect(screen.getByRole('button', { name: 'Jump' })).toBeInTheDocument();
  });

  it('fires onClick when pressed', async () => {
    const onClick = vi.fn();
    render(
      <FloatingActionButton visible={true} onClick={onClick} label="Go" ariaLabel="Go bottom" />,
    );
    fireEvent.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
