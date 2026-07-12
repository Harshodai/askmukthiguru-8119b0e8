import { motion } from 'framer-motion';
import { useMemo, useRef, useEffect } from 'react';

interface Particle {
  id: number;
  x: number;
  y: number;
  delay: number;
  duration: number;
  size: number;
  opacity: number;
}

export interface BackgroundParticlesProps {
  count?: number;
  primaryColor?: string;
  secondaryColor?: string;
  className?: string;
}

function hsla(hsl: string, a: number): string {
  const match = hsl.match(/hsl\s*\(\s*([\d.]+)(?:deg|grad|rad|turn)?[\s,]+([\d.]+)%[\s,]+([\d.]+)%\s*\)?/i);
  if (match) {
    const [_, h, s, l] = match;
    return `hsla(${h}, ${s}%, ${l}%, ${a})`;
  }
  return `${hsl.replace(')', '')} / ${a})`;
}

export const BackgroundParticles = ({
  count,
  primaryColor = 'hsl(43 96% 56%)',
  secondaryColor = 'hsl(45 100% 70%)',
  className = 'absolute inset-0 overflow-hidden pointer-events-none z-0',
}: BackgroundParticlesProps) => {
  // Detect low-power devices, reduced motion, and small viewports.
  // Heavy particle counts with large box-shadow glows were causing scroll
  // jank and full-page blackouts on mobile (GPU compositor OOM). We now
  // cap counts aggressively and remove the outer glow ring on mobile.
  const { effectiveCount, isMobile, prefersReducedMotion } = useMemo(() => {
    if (typeof window === 'undefined') {
      return { effectiveCount: count ?? 40, isMobile: false, prefersReducedMotion: false };
    }
    const mobile = window.matchMedia('(max-width: 768px)').matches;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const base = count ?? (mobile ? 14 : 40);
    return { effectiveCount: reduced ? 0 : base, isMobile: mobile, prefersReducedMotion: reduced };
  }, [count]);

  const heightRef = useRef(typeof window !== 'undefined' ? window.innerHeight : 800);

  useEffect(() => {
    const onResize = () => { heightRef.current = window.innerHeight; };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const particles = useMemo<Particle[]>(() => {
    return Array.from({ length: effectiveCount }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * 110 - 10,
      delay: Math.random() * 6,
      duration: 16 + Math.random() * 18,
      size: (isMobile ? 4 : 6) + Math.random() * (isMobile ? 6 : 12),
      opacity: 0.6 + Math.random() * 0.3,
    }));
  }, [effectiveCount, isMobile]);

  if (prefersReducedMotion || effectiveCount === 0) {
    return <div className={className} />;
  }

  return (
    <div className={className}>
      {particles.map((particle) => {
        const o = particle.opacity;
        const glow = isMobile
          ? `0 0 ${particle.size * 2}px ${hsla(primaryColor, o * 0.5)}`
          : `0 0 ${particle.size * 4}px ${hsla(primaryColor, o * 0.7)}, 0 0 ${particle.size * 8}px ${hsla(primaryColor, o * 0.2)}`;
        return (
          <motion.div
            key={particle.id}
            className="absolute rounded-full"
            style={{
              left: `${particle.x}%`,
              bottom: `${particle.y}%`,
              width: particle.size,
              height: particle.size,
              background: `radial-gradient(circle, ${hsla(primaryColor, o)}, ${hsla(secondaryColor, o * 0.5)})`,
              boxShadow: glow,
              willChange: 'transform, opacity',
            }}
            initial={{ opacity: 0, y: 0 }}
            animate={{
              y: [0, -heightRef.current - 120],
              opacity: [0, o, o, 0],
            }}
            transition={{
              duration: particle.duration,
              repeat: Infinity,
              delay: particle.delay,
              ease: 'linear',
              times: [0, 0.08, 0.92, 1],
            }}
          />
        );
      })}
    </div>
  );
};
