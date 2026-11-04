import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

// T1-19 (PRD-009): the client must not post "Summarize our conversation so far."
// to /api/chat; the backend bounds context itself.
describe('no client-side summary call (T1-19)', () => {
  for (const rel of ['../../lib/chat/transport.ts', '../../lib/chat/index.ts', '../../components/chat/ChatInterface.tsx']) {
    it(`${rel} has no summary call`, () => {
      const src = readFileSync(resolve(__dirname, rel), 'utf8');
      expect(src).not.toMatch(/Summarize our conversation/);
      expect(src).not.toMatch(/generateSummary|maybeSummarize/);
    });
  }
});
