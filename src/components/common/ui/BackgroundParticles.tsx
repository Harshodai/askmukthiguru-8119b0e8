import { motion } from 'framer-motion';
import { useMemo } from 'react';

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

export const BackgroundParticles = ({
  count = 35,
  primaryColor = 'hsl(43 96% 56%',
  secondaryColor = 'hsl(45 100% 70%',
  className = 'absolute inset-0 overflow-hidden pointer-events-none',
}: BackgroundParticlesProps) => {
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
        const c1 = `${primaryColor} / ${particle.opacity}`;
        const c2 = `${secondaryColor} / ${particle.opacity * 0.6}`;
        const glow = `${primaryColor} / ${particle.opacity * 0.6}`;
        const softGlow = `${primaryColor} / ${particle.opacity * 0.2}`;
        return (
          <motion.div
            key={particle.id}
            className="absolute rounded-full"
            style={{
              left: `${particle.x}%`,
              bottom: '-20px',
              width: particle.size,
              height: particle.size,
              background: `radial-gradient(circle, ${c1}, ${c2})`,
              boxShadow: `0 0 ${particle.size * 4}px ${glow}, 0 0 ${particle.size * 8}px ${softGlow}`,
            }}
            animate={{
              y: [0, -window.innerHeight - 100],
              opacity: [0, particle.opacity, particle.opacity, 0],
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
