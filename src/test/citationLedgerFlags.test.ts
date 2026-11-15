import { describe, expect, it } from 'vitest';
import { citationLedgerFlags } from '@/lib/chatStorage';

// 2026-11-13 audit: the ledger recorded a citation with no rights flag as
// 'licensed' and one with no speaker flag as voice-verified.
describe('citationLedgerFlags', () => {
  it('records explicit server flags', () => {
    expect(citationLedgerFlags({ rightsCleared: true, speakerVerified: true })).toEqual({
      rights_status: 'cleared',
      speaker_verified: true,
    });
  });

  it('never upgrades an absent flag', () => {
    expect(citationLedgerFlags({})).toEqual({
      rights_status: 'unverified',
      speaker_verified: false,
    });
  });

  it('keeps an explicit false', () => {
    expect(citationLedgerFlags({ rightsCleared: false, speakerVerified: false })).toEqual({
      rights_status: 'unverified',
      speaker_verified: false,
    });
  });
});
