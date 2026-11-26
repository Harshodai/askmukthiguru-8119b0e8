import { describe, it, expect } from 'vitest';
import { createProvenanceManifestFromMessage } from '@/types/provenance';
import type { Message } from '@/lib/chatStorage';

describe('Provenance disclosure for verbatim first-person teacher clips', () => {
  it('does not mislabel first_person_verbatim_clip_gate clips as AI-synthesized', () => {
    const message: Message = {
      id: 'msg-fp-1',
      role: 'guru',
      content: 'Peace is not the absence of noise; it is the absence of inner conflict.',
      timestamp: new Date('2026-11-24T00:00:00Z'),
      verification: {
        passed: true,
        direct: false,
        method: 'first_person_verbatim_clip_gate',
        citations_verified: true,
        citation_integrity_verified: true,
        evidence_set_supported: true,
      },
      citations: [
        {
          title: 'On Inner Peace',
          source: 'Sri Preethaji',
          url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s',
          videoId: 'dQw4w9WgXcQ',
          isVerbatim: true,
          rightsCleared: true,
          speakerVerified: true,
          quote: 'Peace is not the absence of noise; it is the absence of inner conflict.',
        },
      ],
    };

    const manifest = createProvenanceManifestFromMessage(message);
    expect(manifest.disclosure.notice).toContain('Verbatim Teaching Clip');
    expect(manifest.disclosure.notice).not.toContain('synthesized by AskMukthiGuru artificial intelligence');
    expect(manifest.grounding.evidenceSupportLabel).toBe('Related, not a direct answer');
  });
});
