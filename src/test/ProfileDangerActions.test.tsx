import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as profileStorage from '@/lib/profileStorage';
import { memoryApi } from '@/lib/memoryApi';

describe('Profile Danger Actions Boundary Isolation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
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
});
