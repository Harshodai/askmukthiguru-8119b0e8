import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parse } from 'yaml';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CrisisLines } from '@/components/common/CrisisLines';
import { INDIA_CRISIS_LINES, US_CRISIS_LINES } from '@/lib/crisisHelplines';

interface RegistryEntry {
  name: string;
  contact: string;
  hours?: string | null;
  last_verified_by_call?: string | null;
}

const registry: RegistryEntry[] = parse(
  readFileSync(resolve(__dirname, '../../config/helplines.yaml'), 'utf8'),
).crisis_helplines;

describe('frontend crisis helplines mirror config/helplines.yaml', () => {
  it.each([...INDIA_CRISIS_LINES, ...US_CRISIS_LINES])('$label matches its registry entry', (line) => {
    const entry = registry.find((e) => e.name === line.registryName);
    expect(entry, `no registry entry named ${line.registryName}`).toBeDefined();
    expect(entry!.contact).toContain(line.display);
    expect(entry!.hours).toBe(line.hours);
    expect(line.tel.replace(/^\+/, '')).toBe(line.display.replace(/\D/g, ''));
  });

  it('leads with the call-verified line', () => {
    const first = registry.find((e) => e.name === INDIA_CRISIS_LINES[0].registryName);
    expect(first?.last_verified_by_call).toBeTruthy();
  });

  it('no locale carries its own copy of the safety-notice numbers', () => {
    const locales = ['as', 'bn', 'en', 'gu', 'hi', 'kn', 'ml', 'mr', 'or', 'pa', 'sa', 'ta', 'te', 'ur'];
    for (const lng of locales) {
      const raw = readFileSync(resolve(__dirname, `../locales/${lng}.json`), 'utf8');
      // The safety notice reads its numbers from crisisHelplines.ts now; a
      // per-locale string is how bn ended up with a stale Vandrevala number.
      expect(JSON.parse(raw).common.crisisNumbers, lng).toBeUndefined();
      expect(raw, lng).not.toMatch(/1860-2662-345|১৮৬০/);
    }
  });

  it('renders every number as a tap-to-call link', () => {
    render(<CrisisLines lines={INDIA_CRISIS_LINES} />);
    for (const line of INDIA_CRISIS_LINES) {
      const link = screen.getByRole('link', { name: `Call ${line.label} at ${line.display}` });
      expect(link).toHaveAttribute('href', `tel:${line.tel}`);
    }
  });
});
