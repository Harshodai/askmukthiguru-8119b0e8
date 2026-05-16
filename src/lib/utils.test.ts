import { describe, it, expect } from 'vitest';
import { cn } from './utils';

describe('cn utility', () => {
  it('merges tailwind classes correctly', () => {
    expect(cn('px-2 py-1', 'bg-red-500')).toBe('px-2 py-1 bg-red-500');
  });

  it('overrides conflicting tailwind classes', () => {
    // twMerge should pick the last one
    expect(cn('bg-red-500', 'bg-blue-500')).toBe('bg-blue-500');
    expect(cn('px-2', 'p-4')).toBe('p-4');
  });

  it('handles conditional classes', () => {
    const isActive = true;
    const isError = false;
    
    expect(
      cn(
        'text-sm',
        isActive && 'font-bold',
        isError && 'text-red-500'
      )
    ).toBe('text-sm font-bold');
  });

  it('handles arrays and objects via clsx', () => {
    expect(cn(['text-sm', 'bg-blue-500'], { 'font-bold': true, 'hidden': false })).toBe('text-sm bg-blue-500 font-bold');
  });
});
