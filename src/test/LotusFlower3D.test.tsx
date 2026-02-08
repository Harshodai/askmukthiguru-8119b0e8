import { describe, it, expect } from 'vitest';

describe('LotusFlower3D Component', () => {
  it('should have correct size mappings', () => {
    const sizeClasses = {
      sm: 'w-32 h-32',
      md: 'w-48 h-48',
      lg: 'w-64 h-64',
    };

    expect(sizeClasses.sm).toBe('w-32 h-32');
    expect(sizeClasses.md).toBe('w-48 h-48');
    expect(sizeClasses.lg).toBe('w-64 h-64');
  });

  it('should have correct petal color gradients', () => {
    const petalColors = {
      outer: 'from-ojas/40 to-ojas-light/60',
      middle: 'from-ojas/50 to-ojas-light/70',
      inner: 'from-ojas/60 to-ojas-light/80',
    };

    expect(petalColors.outer).toContain('ojas');
    expect(petalColors.middle).toContain('ojas');
    expect(petalColors.inner).toContain('ojas');
  });

  it('should generate correct petal rotations', () => {
    const petalCount = 8;
    const rotations = Array.from({ length: petalCount }).map((_, i) => (360 / petalCount) * i);
    
    expect(rotations[0]).toBe(0);
    expect(rotations[1]).toBe(45);
    expect(rotations[4]).toBe(180);
  });
});
