import { motion } from 'framer-motion';
import { useMemo, useRef, useEffect } from 'react';

interface Particle {
  id: number;
  x: number;
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
  return `${hsl.replace(')', '')} / ${a})`;
}

export const BackgroundParticles = ({
  count = 35,
  primaryColor = 'hsl(43 96% 56%)',
  secondaryColor = 'hsl(45 100% 70%)',
  className = 'absolute inset-0 overflow-hidden pointer-events-none',
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
      delay: Math.random() * 12,
      duration: 10 + Math.random() * 12,
      size: 4 + Math.random() * 6,
      opacity: 0.5 + Math.random() * 0.4,
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
              bottom: '-20px',
              width: particle.size,
              height: particle.size,
              background: `radial-gradient(circle, ${hsla(primaryColor, o)}, ${hsla(secondaryColor, o * 0.6)})`,
              boxShadow: `0 0 ${particle.size * 4}px ${hsla(primaryColor, o * 0.6)}, 0 0 ${particle.size * 8}px ${hsla(primaryColor, o * 0.2)}`,
            }}
            animate={{
              y: [0, -heightRef.current - 100],
              opacity: [0, o, o, 0],
            }}
            transition={{
              duration: particle.duration,
              repeat: Infinity,
              delay: particle.delay,
              ease: 'linear',
            }}
          />
        );
      })}
    </div>
  );
};
