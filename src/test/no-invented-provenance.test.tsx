/**
 * Faculty-readiness review 2026-10-05, root-cause classes:
 *
 * 1. Helpline numbers retyped into copy. config/helplines.yaml is the single
 *    source; src/lib/crisisHelplines.ts mirrors it. The Terms page carried its
 *    own numbers in all 14 locales and 12 had drifted (non-24/7 line first,
 *    no Tele-MANAS, no 112; Tamil had none). Numbers now render from the
 *    registry, and no locale string may contain one.
 * 2. Teacher credit invented when the speaker is unknown. A missing speaker
 *    rendered as "Sri Krishnaji / Sri Preethaji"; landing-page summaries were
 *    shown as quotation-marked blockquotes credited to a teacher.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { INDIA_CRISIS_LINES } from '@/lib/crisisHelplines';

const LOCALES_DIR = join(__dirname, '..', 'locales');
const PHONE_RE = /9152987821|9999\s?666\s?555|14416|1800-?891-?4416|\+91|\b112\b|\b988\b/;

function strings(node: unknown, path = ''): Array<[string, string]> {
  if (typeof node === 'string') return [[path, node]];
  if (node && typeof node === 'object') {
    return Object.entries(node as Record<string, unknown>).flatMap(([k, v]) =>
      strings(v, path ? `${path}.${k}` : k),
    );
  }
  return [];
}

describe('helpline numbers come only from the registry', () => {
  const files = readdirSync(LOCALES_DIR).filter((f) => f.endsWith('.json'));

  it('found every locale', () => {
    expect(files.length).toBeGreaterThanOrEqual(14);
  });

  it.each(files)('%s carries no phone numbers in translatable copy', (file) => {
    const data = JSON.parse(readFileSync(join(LOCALES_DIR, file), 'utf-8'));
    const offenders = strings(data).filter(([, value]) => PHONE_RE.test(value));
    expect(offenders).toEqual([]);
  });

  it('the Terms page renders the registry lines', async () => {
    const { default: TermsPage } = await import('@/pages/TermsPage');
    render(
      <MemoryRouter>
        <TermsPage />
      </MemoryRouter>,
    );
    const block = screen.getByTestId('terms-crisis-lines');
    for (const line of INDIA_CRISIS_LINES) {
      expect(block.textContent).toContain(line.display);
    }
  });
});

describe('no teacher credit without a recorded speaker', () => {
  const read = (rel: string) => readFileSync(join(__dirname, '..', rel), 'utf-8');

  it('the source inspector does not fall back to a teacher name', () => {
    const src = read('components/chat/LinkSearchModal.tsx');
    expect(src).not.toMatch(/speaker\s*(\|\||\?\?)\s*['"`]Sri/);
    expect(src).toContain('resolveAttributionLabel');
  });

  it('landing summaries are not rendered as quotations', async () => {
    const { SampleWisdomSection } = await import('@/components/landing/SampleWisdomSection');
    const { container } = render(<SampleWisdomSection />);
    expect(container.querySelector('blockquote')).toBeNull();
    const text = screen.getByTestId('wisdom-paraphrase').textContent ?? '';
    expect(text.startsWith('"')).toBe(false);
    expect(container.textContent).toMatch(/not a direct quote/i);
  });
});
