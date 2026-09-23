import type { NavigateFunction, Location } from 'react-router-dom';

const SAFE_RETURN_PATHS = new Set(['/chat', '/practices', '/']);
const CHAT_OWNED_PATHS = new Set([
  '/profile',
  '/notebooks',
  '/second-brain',
  '/knowledge-graph',
  '/wisdom-map',
  '/reflections',
  '/practices',
]);

export interface ChatOriginState {
  returnTo?: string;
  conversationId?: string;
  conceptQuery?: string;
}

export function buildChatOwnedPath(
  pathname: string,
  options: { conversationId?: string; conceptQuery?: string; tab?: string } = {},
): string {
  const params = new URLSearchParams();
  params.set('returnTo', '/chat');
  if (options.conversationId) params.set('conversation', options.conversationId);
  if (options.conceptQuery && pathname === '/knowledge-graph') params.set('q', options.conceptQuery);
  if (options.tab) params.set('tab', options.tab);
  return `${pathname}?${params.toString()}`;
}

export function isChatOwnedRoute(pathname: string, search: string): boolean {
  const returnTo = new URLSearchParams(search).get('returnTo');
  return returnTo === '/chat' && [...CHAT_OWNED_PATHS].some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );
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
