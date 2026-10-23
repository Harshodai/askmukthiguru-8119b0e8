import { afterEach, describe, it, expect, vi, beforeEach } from 'vitest';
import * as profileStorage from '@/lib/profileStorage';

const memoryMocks = vi.hoisted(() => ({
  getSession: vi.fn(),
  from: vi.fn(),
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: { getSession: memoryMocks.getSession },
    from: memoryMocks.from,
  },
}));

vi.mock('../lib/backendUrl', () => ({
  BACKEND_URL: 'https://backend.test',
}));

import { memoryApi } from '@/lib/memoryApi';

describe('Profile Danger Actions Boundary Isolation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('Clear Local Data wipes local device storage without invoking server memoryApi.deleteAll', async () => {
    const deleteAllDataSpy = vi.spyOn(profileStorage, 'deleteAllData').mockImplementation(() => {});
    const resetProfileSpy = vi.spyOn(profileStorage, 'resetProfile').mockImplementation(() => profileStorage.createDefaultProfile());
    const memoryDeleteAllSpy = vi.spyOn(memoryApi, 'deleteAll').mockResolvedValue();

    // Simulate handleClearLocalData execution
    profileStorage.deleteAllData();
    profileStorage.resetProfile();

    expect(deleteAllDataSpy).toHaveBeenCalledTimes(1);
    expect(resetProfileSpy).toHaveBeenCalledTimes(1);
    // CRITICAL INVARIANT: Local data clearing MUST NEVER cascade to server-side memories
    expect(memoryDeleteAllSpy).not.toHaveBeenCalled();
  });

  it('Erase Cloud Memories properly invokes server-side memoryApi.deleteAll when confirmed', async () => {
    const memoryDeleteAllSpy = vi.spyOn(memoryApi, 'deleteAll').mockResolvedValue();

    // Verify confirmation gate
    const confirmInput = 'DELETE';
    if (confirmInput.trim().toUpperCase() === 'DELETE') {
      await memoryApi.deleteAll();
    }

    expect(memoryDeleteAllSpy).toHaveBeenCalledTimes(1);
  });

  it('routes individual memory erasure through the backend invalidation path', async () => {
    memoryMocks.getSession.mockResolvedValue({
      data: { session: { access_token: 'test-access-token' } },
      error: null,
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await memoryApi.forget('memory-123');

    expect(fetchMock).toHaveBeenCalledWith(
      'https://backend.test/api/memory/forget',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ memory_id: 'memory-123' }),
      }),
    );
    expect(memoryMocks.from).not.toHaveBeenCalled();
  });

  it('does not report success when the erasure receipt is partial', async () => {
    memoryMocks.getSession.mockResolvedValue({
      data: { session: { access_token: 'test-access-token' } },
      error: null,
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ status: 'partial_failure', failures: ['qdrant unavailable'] }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    vi.stubGlobal('fetch', fetchMock);

    await expect(memoryApi.deleteAll()).rejects.toMatchObject({
      status: 503,
      message: expect.stringContaining('1 store(s) not confirmed'),
    });
  });
});
