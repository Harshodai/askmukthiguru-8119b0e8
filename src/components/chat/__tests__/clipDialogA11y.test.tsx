/**
 * NEW-A11Y-3 (A11Y-04): the clip dialog needs an accessible name and
 * description. Radix warns ("DialogContent requires a DialogTitle") and the
 * dialog is announced as an unnamed dialog when they are missing.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { cleanup, render, screen } from '@testing-library/react';
import { DiscourseVideoModal } from '@/components/chat/CitationCard';

const CITATION = {
  index: 1,
  url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
  title: 'The Four Sacred Secrets — On Stillness',
  speaker: 'Sri Krishnaji',
  playbackStartSeconds: 76,
  playbackEndSeconds: 165,
  quote: 'Be still, and the truth reveals itself.',
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('clip dialog accessible name (NEW-A11Y-3)', () => {
  it('names the dialog with the clip title and describes it', () => {
    const warn = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const warnLog = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    render(<DiscourseVideoModal citation={CITATION} isOpen onClose={() => undefined} />);

    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAccessibleName(/The Four Sacred Secrets/);
    expect(dialog).toHaveAccessibleDescription(/\S+/);

    const radixComplaints = [...warn.mock.calls, ...warnLog.mock.calls]
      .map((c) => String(c[0]))
      .filter((m) => /DialogTitle|Description/.test(m));
    expect(radixComplaints).toEqual([]);
  });
});

function tsxFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return tsxFiles(full);
    return full.endsWith('.tsx') && !full.includes('__tests__') ? [full] : [];
  });
}

describe('every dialog is named (NEW-A11Y-3 guard)', () => {
  it('each file that renders <DialogContent> also renders a <DialogTitle>', () => {
    const offenders = tsxFiles(join(process.cwd(), 'src'))
      .filter((f) => !f.includes(`${join('components', 'ui')}`))
      .filter((f) => {
        const text = readFileSync(f, 'utf8');
        return text.includes('<DialogContent') && !text.includes('<DialogTitle');
      });
    expect(offenders).toEqual([]);
  });
});
