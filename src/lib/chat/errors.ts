import type { AIErrorCode } from './types';

export function httpStatusToErrorCode(status: number, bodyQuotaExceeded?: boolean): AIErrorCode {
  if (status === 401 || status === 403) return 'unauthorized';
  if (status === 504 || status === 408) return 'timeout';
  if (status === 429) return bodyQuotaExceeded ? 'quota_exceeded' : 'rate_limited';
  if (status >= 500) return 'server_error';
  return 'unknown';
}
