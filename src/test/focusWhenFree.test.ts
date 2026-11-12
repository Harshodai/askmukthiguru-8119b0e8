import { afterEach, describe, expect, it } from 'vitest';
import { focusIsFree, focusWhenFree } from '@/lib/focusWhenFree';

afterEach(() => {
  document.body.innerHTML = '';
});

const frame = () => new Promise((r) => requestAnimationFrame(() => r(null)));

describe('focusIsFree', () => {
  it('is true for body, null, detached and disabled elements', () => {
    expect(focusIsFree(null)).toBe(true);
    expect(focusIsFree(document.body)).toBe(true);
    const b = document.createElement('button');
    expect(focusIsFree(b)).toBe(true); // detached
    document.body.append(b);
    b.disabled = true;
    expect(focusIsFree(b)).toBe(true);
  });
  it('is false for a live, enabled element', () => {
    const a = document.createElement('a');
    a.href = '#x';
    document.body.append(a);
    expect(focusIsFree(a)).toBe(false);
  });
});

describe('focusWhenFree', () => {
  it('focuses a target that mounts a few frames late', async () => {
    const input = document.createElement('textarea');
    let mounted = false;
    focusWhenFree(() => (mounted ? input : null));
    await frame();
    document.body.append(input);
    mounted = true;
    await frame();
    await frame();
    expect(document.activeElement).toBe(input);
  });

  it('leaves focus alone when the seeker put it elsewhere', async () => {
    const link = document.createElement('a');
    link.href = '#x';
    const input = document.createElement('textarea');
    document.body.append(link, input);
    link.focus();
    focusWhenFree(() => input);
    await frame();
    await frame();
    expect(document.activeElement).toBe(link);
  });

  it('with waitForFree, waits for the old holder to go away, then focuses', async () => {
    const old = document.createElement('button');
    const input = document.createElement('textarea');
    document.body.append(old, input);
    old.focus();
    focusWhenFree(() => input, { waitForFree: true });
    await frame();
    expect(document.activeElement).toBe(old);
    old.remove();
    await frame();
    await frame();
    expect(document.activeElement).toBe(input);
  });

  it('can be cancelled', async () => {
    const input = document.createElement('textarea');
    document.body.append(input);
    const cancel = focusWhenFree(() => input);
    cancel();
    await frame();
    await frame();
    expect(document.activeElement).toBe(document.body);
  });
});
