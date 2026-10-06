import { act, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { useDialogFocus } from '@/hooks/useDialogFocus';

function Harness({ onEscape }: { onEscape?: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useDialogFocus<HTMLDivElement>(open, {
    onEscape: () => {
      onEscape?.();
      setOpen(false);
    },
  });
  return (
    <>
      <button onClick={() => setOpen(true)}>opener</button>
      <button>behind</button>
      {open && (
        <div ref={ref} role="dialog" aria-modal="true">
          <button>first</button>
          <button>last</button>
        </div>
      )}
    </>
  );
}

const flushFrame = () => act(() => new Promise((r) => requestAnimationFrame(() => r(null))));

describe('useDialogFocus', () => {
  it('moves focus in, traps Tab both ways, closes on Escape and restores focus', async () => {
    const onEscape = vi.fn();
    render(<Harness onEscape={onEscape} />);
    const opener = screen.getByText('opener');
    opener.focus();
    fireEvent.click(opener);
    await flushFrame();
    expect(document.activeElement).toBe(screen.getByText('first'));

    screen.getByText('last').focus();
    fireEvent.keyDown(document.activeElement!, { key: 'Tab' });
    expect(document.activeElement).toBe(screen.getByText('first'));

    fireEvent.keyDown(document.activeElement!, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(screen.getByText('last'));

    // Focus that escaped to the page is pulled back in on the next Tab.
    screen.getByText('behind').focus();
    fireEvent.keyDown(document.activeElement!, { key: 'Tab' });
    expect(document.activeElement).toBe(screen.getByText('first'));

    fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
    expect(onEscape).toHaveBeenCalledOnce();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(opener);
  });
});
