/**
 * NEW-LOV-03: the relative-/api rule (T1-16) must catch every call form a
 * generated file may use, not only fetch().
 */
import { describe, expect, it } from 'vitest';
import { ESLint } from 'eslint';

async function messages(code: string) {
  const eslint = new ESLint({ cwd: process.cwd() });
  const [result] = await eslint.lintText(code, { filePath: 'src/__lint_probe__.ts' });
  return result.messages.filter((m) => m.ruleId === 'no-restricted-syntax');
}

describe('relative /api calls are rejected (T1-16, NEW-LOV-03)', () => {
  it.each([
    ["fetch('/api/chat')", 'fetch literal'],
    ['fetch(`/api/chat/${1}`)', 'fetch template'],
    ["new EventSource('/api/stream')", 'EventSource'],
    ["navigator.sendBeacon('/api/telemetry', '{}')", 'sendBeacon'],
  ])('flags %s (%s)', async (code) => {
    expect((await messages(code)).length).toBeGreaterThan(0);
  });

  it('allows the backend URL helper', async () => {
    const code = "import { BACKEND_URL } from '@/lib/backendUrl';\nfetch(`${BACKEND_URL}/api/chat`);\n";
    expect(await messages(code)).toEqual([]);
  });
});
