/**
 * NEW-A11Y-8 (A11Y-10, WCAG 3.2.6 Consistent Help): a persistent "Get help now"
 * control opens the same helpline list the safety notice uses. Numbers come from
 * src/lib/crisisHelplines.ts only; this component holds none.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { GetHelpNow } from '@/components/common/GetHelpNow';
import { INDIA_CRISIS_LINES } from '@/lib/crisisHelplines';

afterEach(() => cleanup());

describe('GetHelpNow', () => {
  it('is a named control and opens the helpline list from crisisHelplines', async () => {
    render(<GetHelpNow />);
    fireEvent.click(screen.getByRole('button', { name: /get help now/i }));

    const dialog = await screen.findByRole('dialog', { name: /get help now/i });
    for (const line of INDIA_CRISIS_LINES) {
      const link = dialog.querySelector(`a[href="tel:${line.tel}"]`);
      expect(link, line.label).not.toBeNull();
    }
    expect(dialog).toHaveAccessibleDescription(/\S+/);
  });

  it('holds no phone number of its own', () => {
    const src = readFileSync(join(process.cwd(), 'src/components/common/GetHelpNow.tsx'), 'utf8');
    expect(src).not.toMatch(/\b\d{3,}[\d\s-]{3,}\b/);
    expect(src).not.toMatch(/tel:/);
  });
});

describe('placement (WCAG 3.2.6: same place on every page)', () => {
  const must: Array<[string, string]> = [
    ['src/components/chat/ChatHeader.tsx', 'chat'],
    ['src/components/layout/AppShell.tsx', 'profile and practices'],
    ['src/components/landing/Navbar.tsx', 'landing and public pages'],
    ['src/pages/AuthPage.tsx', 'auth'],
  ];
  it.each(must)('%s renders <GetHelpNow /> (%s)', (file) => {
    const src = readFileSync(join(process.cwd(), file), 'utf8');
    expect(src).toContain('<GetHelpNow');
  });
});
