import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { PUBLIC_APP_URL } from '@/lib/domain';

const sitemap = readFileSync(resolve(process.cwd(), 'public/sitemap.xml'), 'utf8');
const urls = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]);

describe('public discovery coverage', () => {
  it('includes the existing Trust page', () => {
    expect(urls).toContain(`${PUBLIC_APP_URL}/trust`);
  });
  it('includes the existing Spirit Guides page', () => {
    expect(urls).toContain(`${PUBLIC_APP_URL}/guides/spirit-guides`);
  });
  it('keeps each public URL unique', () => {
    expect(new Set(urls).size).toBe(urls.length);
  });
});