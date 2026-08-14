import type { NavigateFunction, Location } from 'react-router-dom';

const SAFE_RETURN_PATHS = new Set(['/chat', '/practices', '/']);

export interface ChatOriginState {
  returnTo?: string;
  conversationId?: string;
  conceptQuery?: string;
}

export function buildChatOwnedPath(
  pathname: string,
  options: { conversationId?: string; conceptQuery?: string } = {},
): string {
  const params = new URLSearchParams();
  params.set('returnTo', '/chat');
  if (options.conversationId) params.set('conversation', options.conversationId);
  if (options.conceptQuery && pathname === '/knowledge-graph') params.set('q', options.conceptQuery);
  return `${pathname}?${params.toString()}`;
}

export function getChatOrigin(location: Pick<Location, 'search'>): ChatOriginState {
  const params = new URLSearchParams(location.search);
  const returnTo = params.get('returnTo') || undefined;
  const conversationId = params.get('conversation') || undefined;
  const conceptQuery = params.get('q') || undefined;
  return { returnTo, conversationId, conceptQuery };
}

export function isSafeReturnPath(path: string | undefined): path is string {
  if (!path || !path.startsWith('/') || path.startsWith('//')) return false;
  const pathname = path.split('?')[0] || '/';
  return SAFE_RETURN_PATHS.has(pathname);
}

export function returnToOrigin(
  navigate: NavigateFunction,
  location: Pick<Location, 'search'>,
  fallback = '/chat',
): void {
  const origin = getChatOrigin(location);
  const target = isSafeReturnPath(origin.returnTo) ? origin.returnTo : fallback;
  const params = new URLSearchParams();
  if (target === '/chat' && origin.conversationId) {
    params.set('conversation', origin.conversationId);
  }
  navigate(params.toString() ? `${target}?${params.toString()}` : target, { replace: true });
}
