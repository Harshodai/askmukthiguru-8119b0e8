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

export const FloatingParticles = () => {
  const particles = useMemo<Particle[]>(() => {
    return Array.from({ length: 25 }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      delay: Math.random() * 10,
      duration: 12 + Math.random() * 10,
      size: 3 + Math.random() * 5,
      opacity: 0.4 + Math.random() * 0.4,
    }));
  }, []);

  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none">
      {particles.map((particle) => (
        <motion.div
          key={particle.id}
          className="absolute rounded-full"
          style={{
            left: `${particle.x}%`,
            bottom: '-20px',
            width: particle.size,
            height: particle.size,
            background: `radial-gradient(circle, hsl(43 96% 56% / ${particle.opacity}), hsl(45 100% 70% / ${particle.opacity * 0.5}))`,
            boxShadow: `0 0 ${particle.size * 3}px hsl(43 96% 56% / ${particle.opacity * 0.4})`,
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
      ))}
    </div>
  );
};
