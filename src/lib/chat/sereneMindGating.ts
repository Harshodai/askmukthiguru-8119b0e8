export function isSevereDistressLevel(level?: string | null): boolean {
  if (!level) return false;
  const normalized = level.trim().toUpperCase();
  return normalized === 'SEVERE' || normalized === 'CRISIS';
}

export function shouldGateSereneMind(opts: {
  blocked?: boolean;
  blockReason?: string | null;
  distressLevel?: string | null;
}): boolean {
  if (!opts.blocked) return false;
  if (opts.blockReason === 'circuit_breaker_open') return false;
  return isSevereDistressLevel(opts.distressLevel);
}
