/**
 * NEW-A11Y-8 (A11Y-12, WCAG 2.2.2): under "reduce motion", looping decorative
 * animations are cancelled. Spinners and anything marked essential stay.
 */
import { describe, expect, it, vi } from 'vitest';
import { cancelDecorativeLoops } from '@/lib/reducedMotionGuard';

function anim(el: Element, iterations: number) {
  return {
    effect: { getComputedTiming: () => ({ iterations }), target: el },
    cancel: vi.fn(),
  };
}

describe('cancelDecorativeLoops', () => {
  it('cancels infinite animations, keeps finite ones, spinners and essential motion', () => {
    document.body.innerHTML = `
      <div id="halo"></div>
      <div id="once"></div>
      <svg class="animate-spin" id="spin"><path id="spinChild"/></svg>
      <div data-motion-essential><span id="inner"></span></div>`;
    const get = (id: string) => document.getElementById(id)!;
    const halo = anim(get('halo'), Infinity);
    const once = anim(get('once'), 1);
    const spin = anim(get('spin'), Infinity);
    const spinChild = anim(get('spinChild'), Infinity);
    const inner = anim(get('inner'), Infinity);
    const doc = {
      getAnimations: () => [halo, once, spin, spinChild, inner],
    } as unknown as Document;

    const n = cancelDecorativeLoops(doc);

    expect(halo.cancel).toHaveBeenCalledTimes(1);
    expect(once.cancel).not.toHaveBeenCalled();
    expect(spin.cancel).not.toHaveBeenCalled();
    expect(spinChild.cancel).not.toHaveBeenCalled();
    expect(inner.cancel).not.toHaveBeenCalled();
    expect(n).toBe(1);
  });

  it('does not throw when the browser has no getAnimations', () => {
    expect(cancelDecorativeLoops({} as Document)).toBe(0);
  });
});
