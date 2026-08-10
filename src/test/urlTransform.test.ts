import { describe, it, expect } from 'vitest';
import { safeUrlTransform } from '@/components/chat/ChatMessage';

describe('safeUrlTransform (markdown href allowlist)', () => {
  it('blocks javascript: hrefs', () => {
    expect(safeUrlTransform('javascript:alert(1)')).toBe('');
    expect(safeUrlTransform('JAVASCRIPT:alert(1)')).toBe('');
  });

  it('blocks data: and vbscript: hrefs', () => {
    expect(safeUrlTransform('data:text/html;base64,PHNjcmlwdD4=')).toBe('');
    expect(safeUrlTransform('vbscript:msgbox(1)')).toBe('');
  });

  it('allows https URLs', () => {
    expect(safeUrlTransform('https://ekam.org/teaching')).toBe('https://ekam.org/teaching');
  });

  it('allows http URLs', () => {
    expect(safeUrlTransform('http://example.com')).toBe('http://example.com');
  });

  it('allows mailto links', () => {
    expect(safeUrlTransform('mailto:dev@askmukthiguru.com')).toBe('mailto:dev@askmukthiguru.com');
  });

  it('allows in-page anchors (#cite-...) used by citation markers', () => {
    expect(safeUrlTransform('#cite-1')).toBe('#cite-1');
    expect(safeUrlTransform('#citation')).toBe('#citation');
  });
});
