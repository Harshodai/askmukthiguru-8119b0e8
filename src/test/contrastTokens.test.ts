/**
 * NEW-A11Y-2 (A11Y-01, A11Y-02, A11Y-03; AC-A11Y-7).
 *
 * 1. The text inks clear WCAG 1.4.3 (4.5:1) on the surfaces they sit on, in the
 *    light and the dark theme, computed from the tokens in src/index.css.
 * 2. The trust-label files never put a fill colour on text. `text-ojas` and
 *    `text-saffron-gold` are the brand gold (1.5:1 on the cream ground),
 *    `text-amber-600` is 3.07:1 and `text-destructive` is 3.3:1 on its tint.
 *    Use `text-ojas-ink`, `text-amber-ink` and `text-destructive-ink`.
 *
 * The guard does not judge icons: an element whose tag is an imported lucide
 * icon (or EkamGoldenOrb) may keep the fill colours.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const ROOT = resolve(__dirname, '..', '..');
const css = readFileSync(resolve(ROOT, 'src/index.css'), 'utf8');

type Rgb = [number, number, number];

function block(start: string): string {
  const i = css.indexOf(start);
  if (i < 0) throw new Error(`block ${start} not found`);
  return css.slice(i, css.indexOf('\n  }', i));
}

function token(blk: string, name: string): Rgb {
  // A theme block may leave a token to :root; fall back to it, as the cascade does.
  const re = new RegExp(`--${name}:\\s*([\\d.]+)\\s+([\\d.]+)%\\s+([\\d.]+)%`);
  const m = re.exec(blk) ?? re.exec(block(':root {'));
  if (!m) throw new Error(`token --${name} missing`);
  return hslToRgb(Number(m[1]), Number(m[2]) / 100, Number(m[3]) / 100);
}

function hslToRgb(h: number, s: number, l: number): Rgb {
  const k = (n: number) => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return [f(0), f(8), f(4)];
}

function lum([r, g, b]: Rgb): number {
  const c = (v: number) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  return 0.2126 * c(r) + 0.7152 * c(g) + 0.0722 * c(b);
}

function ratio(a: Rgb, b: Rgb): number {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const over = (fg: Rgb, bg: Rgb, alpha: number): Rgb =>
  [0, 1, 2].map((i) => fg[i] * alpha + bg[i] * (1 - alpha)) as Rgb;

const AMBER_500: Rgb = [245 / 255, 158 / 255, 11 / 255]; // tailwind amber-500, the tint base

describe.each([
  ['light', ':root {'],
  ['dark', '.dark {'],
])('text inks on the %s theme', (_theme, start) => {
  const blk = block(start);
  const card = token(blk, 'card');
  const ground = token(blk, 'background');
  const cases: [string, Rgb, Rgb][] = [
    ['ojas-gold-ink', token(blk, 'ojas-gold-ink'), token(blk, 'ojas-gold')],
    ['destructive-ink', token(blk, 'destructive-ink'), token(blk, 'destructive')],
    ['amber-ink', token(blk, 'amber-ink'), AMBER_500],
  ];
  it.each(cases)('%s reaches 4.5:1 on card, ground and its own 10% tint', (_n, ink, base) => {
    expect(ratio(ink, card)).toBeGreaterThanOrEqual(4.5);
    expect(ratio(ink, ground)).toBeGreaterThanOrEqual(4.5);
    expect(ratio(ink, over(base, card, 0.1))).toBeGreaterThanOrEqual(4.5);
  });
});

const GUARDED = [
  'src/components/chat/ChatMessage.tsx',
  'src/components/chat/CitationCard.tsx',
  'src/pages/TeacherWords.tsx',
  'src/types/provenance.ts',
  'src/components/compliance/EuAiBadge.tsx',
];
// A bare fill colour as a text colour: not `-ink`, `-light`, `-dark`, `-foreground`, and not
// behind a variant prefix such as hover: or marker: (a state or a list marker, not resting text).
const FILL_AS_TEXT = /(?<![\w:-])text-(?:ojas|saffron-gold|amber-600|destructive)(?![\w-])/g;

function iconNames(src: string): Set<string> {
  const names = new Set<string>(['EkamGoldenOrb']);
  for (const m of src.matchAll(/import\s*\{([^}]+)\}\s*from\s*['"]lucide-react['"]/g)) {
    for (const part of m[1].split(',')) names.add(part.split(' as ').pop()!.trim());
  }
  return names;
}

export function fillColourTextUses(src: string): { line: number; text: string }[] {
  const icons = iconNames(src);
  const hits: { line: number; text: string }[] = [];
  for (const m of src.matchAll(FILL_AS_TEXT)) {
    const before = src.slice(0, m.index);
    const tag = [...before.matchAll(/<([A-Za-z][\w.]*)/g)].pop()?.[1] ?? '';
    if (icons.has(tag)) continue;
    const line = before.split('\n').length;
    hits.push({ line, text: src.split('\n')[line - 1].trim().slice(0, 120) });
  }
  return hits;
}

describe('trust-label files do not use fill colours as text colours', () => {
  it.each(GUARDED)('%s', (file) => {
    const src = readFileSync(resolve(ROOT, file), 'utf8');
    expect(fillColourTextUses(src)).toEqual([]);
  });

  it('the guard itself flags a bare gold span and ignores a lucide icon', () => {
    const sample = `import { Sparkles } from 'lucide-react';
      <span className="text-ojas">x</span>
      <Sparkles className="h-4 w-4 text-ojas" />`;
    expect(fillColourTextUses(sample)).toHaveLength(1);
  });
});
