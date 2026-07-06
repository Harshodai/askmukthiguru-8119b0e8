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
  count = 80,
  primaryColor = 'hsl(43 96% 56%)',
  secondaryColor = 'hsl(45 100% 70%)',
  className = 'absolute inset-0 overflow-hidden pointer-events-none z-0',
}: BackgroundParticlesProps) => {
  const heightRef = useRef(window.innerHeight);

  useEffect(() => {
    const onResize = () => { heightRef.current = window.innerHeight; };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const particles = useMemo<Particle[]>(() => {
    return Array.from({ length: count }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * 110 - 10,
      delay: Math.random() * 6,
      duration: 16 + Math.random() * 18,
      size: 6 + Math.random() * 14,
      opacity: 0.7 + Math.random() * 0.3,
    }));
  }, [count]);

  return (
    <div className={className}>
      {particles.map((particle) => {
        const o = particle.opacity;
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
              boxShadow: `0 0 ${particle.size * 5}px ${hsla(primaryColor, o * 0.8)}, 0 0 ${particle.size * 10}px ${hsla(primaryColor, o * 0.25)}`,
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
