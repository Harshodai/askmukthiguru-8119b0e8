import type { AIErrorCode } from './types';

export function httpStatusToErrorCode(status: number): AIErrorCode {
  if (status === 401 || status === 403) return 'unauthorized';
  if (status === 504 || status === 408) return 'timeout';
  if (status === 429) return 'rate_limited';
  if (status >= 500) return 'server_error';
  return 'unknown';
}
