/**
 * Faculty review P1-7: the public URL lived in several files and they named
 * three different hosts (Lovable, Vercel, askmukthiguru.com). PUBLIC_APP_URL in
 * src/lib/domain.ts is now the one source; every static copy must equal it, so
 * moving to a custom domain is one edit plus whatever this test points at.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  CONTACT_EMAIL,
  PUBLIC_APP_URL,
  getHelloEmail,
  getPrivacyEmail,
  getSupportEmail,
} from '@/lib/domain';

const ROOT = join(__dirname, '..', '..');
const read = (rel: string) => readFileSync(join(ROOT, rel), 'utf-8');
const host = new URL(PUBLIC_APP_URL).host;

describe('PUBLIC_APP_URL is the only public host', () => {
  it.each(['index.html', 'public/robots.txt', 'public/sitemap.xml'])(
    '%s names no other askmukthiguru host',
    (rel) => {
      const hosts = new Set(
        [...read(rel).matchAll(/https:\/\/(?:oauth\.)?([a-z0-9.-]*askmukthiguru[a-z0-9.-]*)/gi)].map((m) => m[1]),
      );
      expect([...hosts]).toEqual([host]);
    },
  );

  it('deploy_railway.sh allows exactly this origin for CORS', () => {
    expect(read('deploy_railway.sh')).toContain(`set_var CORS_ORIGINS "${PUBLIC_APP_URL}"`);
  });

  it('.env.example sets VITE_PUBLIC_APP_URL to it', () => {
    expect(read('.env.example')).toContain(`VITE_PUBLIC_APP_URL=${PUBLIC_APP_URL}`);
  });
});

describe('contact mail goes to one real inbox', () => {
  it('privacy, support and hello all use CONTACT_EMAIL, not the host', () => {
    // Derived addresses such as privacy@askmukthiguru.lovable.app receive no mail.
    for (const email of [getPrivacyEmail(), getSupportEmail(), getHelloEmail()]) {
      expect(email).toBe(CONTACT_EMAIL);
      expect(email).not.toContain(host);
    }
  });

  it('no page hardcodes its own copy of the address', () => {
    const literal = read('src/pages/ProfilePage.tsx');
    expect(literal).not.toContain(`mailto:${CONTACT_EMAIL}`);
    expect(read('.env.example')).toContain(`VITE_CONTACT_EMAIL=${CONTACT_EMAIL}`);
  });
});
