import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const source = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../pages/SecondBrainPage.tsx'),
  'utf8',
);

describe('Second Brain unavailable state', () => {
  it('explains the separate Profile Memory store and offers a fallback link', () => {
    expect(source).toContain('My Reflections is an encrypted vault, separate from Profile Memory.');
    expect(source).toContain('View Profile Memory');
    expect(source).toContain('to="/profile?tab=memory"');
  });
});
