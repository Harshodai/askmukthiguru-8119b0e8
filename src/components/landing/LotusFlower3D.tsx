import { motion } from 'framer-motion';
import { useMemo } from 'react';

interface LotusFlower3DProps {
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

// Seeded random for consistent sparkle positions
const seededRandom = (seed: number) => {
  const x = Math.sin(seed * 9999) * 10000;
  return x - Math.floor(x);
};

export const LotusFlower3D = ({ className = '', size = 'md' }: LotusFlower3DProps) => {
  const sizeClasses = {
    sm: 'w-32 h-32',
    md: 'w-48 h-48',
    lg: 'w-64 h-64',
  };

  // Memoize sparkle positions for consistent rendering
  const sparkles = useMemo(() => {
    return Array.from({ length: 4 }).map((_, i) => ({
      left: `${35 + seededRandom(i * 10) * 30}%`,
      top: `${25 + seededRandom(i * 20) * 30}%`,
      delay: i * 0.6,
    }));
  }, []);

  // Create simplified petal layers
  const outerPetals = useMemo(() => {
    return Array.from({ length: 8 }).map((_, i) => ({
      rotation: (360 / 8) * i,
      delay: 0.08 * i,
    }));
  }, []);

  const innerPetals = useMemo(() => {
    return Array.from({ length: 6 }).map((_, i) => ({
      rotation: (360 / 6) * i + 30,
      delay: 0.1 * i + 0.5,
    }));
  }, []);

  return (
    <div 
      className={`relative ${sizeClasses[size]} ${className}`} 
      style={{ perspective: '800px' }}
      data-testid="lotus-flower-3d"
    >
      {/* Soft Glow Effect */}
      <motion.div
        className="absolute inset-0 rounded-full"
        style={{
          background: 'radial-gradient(circle, hsl(var(--ojas-gold) / 0.25) 0%, transparent 70%)',
          filter: 'blur(20px)',
        }}
        animate={{
          scale: [1, 1.08, 1],
          opacity: [0.6, 0.8, 0.6],
        }}
        transition={{
          duration: 4,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
      />

      {/* Main Lotus Container */}
      <motion.div
        className="absolute inset-0 flex items-center justify-center"
        style={{ 
          transformStyle: 'preserve-3d',
        }}
        initial={{ rotateX: 40, scale: 0.6, opacity: 0 }}
        animate={{ rotateX: 20, scale: 1, opacity: 1 }}
        transition={{ duration: 1.2, ease: 'easeOut' }}
      >
        {/* Outer Petals Layer */}
        <div 
          className="absolute inset-0 flex items-center justify-center"
          style={{ transformStyle: 'preserve-3d' }}
        >
          {outerPetals.map(({ rotation, delay }, i) => (
            <motion.div
              key={`outer-${i}`}
              className="absolute"
              style={{
                width: '35%',
                height: '45%',
                transformStyle: 'preserve-3d',
                transform: `rotateZ(${rotation}deg) translateY(-30%) rotateX(30deg)`,
                transformOrigin: 'center bottom',
              }}
              initial={{ rotateX: 70, opacity: 0 }}
              animate={{ rotateX: 30, opacity: 1 }}
              transition={{
                duration: 1,
                delay,
                ease: 'easeOut',
              }}
            >
              <motion.div
                className="w-full h-full rounded-t-full"
                style={{
                  background: 'linear-gradient(to top, hsl(var(--ojas-gold) / 0.5), hsl(var(--ojas-gold-light) / 0.7))',
                  boxShadow: '0 0 15px hsl(var(--ojas-gold) / 0.25)',
                  backfaceVisibility: 'hidden',
                }}
                animate={{
                  rotateZ: [-1.5, 1.5, -1.5],
                }}
                transition={{
                  duration: 3 + i * 0.3,
                  repeat: Infinity,
                  ease: 'easeInOut',
                }}
              />
            </motion.div>
          ))}
        </div>

        {/* Inner Petals Layer */}
        <div 
          className="absolute inset-0 flex items-center justify-center"
          style={{ transformStyle: 'preserve-3d' }}
        >
          {innerPetals.map(({ rotation, delay }, i) => (
            <motion.div
              key={`inner-${i}`}
              className="absolute"
              style={{
                width: '28%',
                height: '38%',
                transformStyle: 'preserve-3d',
                transform: `rotateZ(${rotation}deg) translateY(-20%) rotateX(45deg) translateZ(15px)`,
                transformOrigin: 'center bottom',
              }}
              initial={{ rotateX: 80, opacity: 0 }}
              animate={{ rotateX: 45, opacity: 1 }}
              transition={{
                duration: 1,
                delay,
                ease: 'easeOut',
              }}
            >
              <motion.div
                className="w-full h-full rounded-t-full"
                style={{
                  background: 'linear-gradient(to top, hsl(var(--ojas-gold) / 0.6), hsl(var(--ojas-gold-light) / 0.85))',
                  boxShadow: '0 0 12px hsl(var(--ojas-gold) / 0.3)',
                  backfaceVisibility: 'hidden',
                }}
                animate={{
                  rotateZ: [1, -1, 1],
                }}
                transition={{
                  duration: 3.5 + i * 0.2,
                  repeat: Infinity,
                  ease: 'easeInOut',
                }}
              />
            </motion.div>
          ))}
        </div>

        {/* Center of Lotus */}
        <motion.div
          className="absolute w-1/5 h-1/5 rounded-full"
          style={{
            background: 'radial-gradient(circle, hsl(var(--ojas-gold)) 0%, hsl(var(--ojas-gold-light)) 60%, transparent 100%)',
            boxShadow: '0 0 25px hsl(var(--ojas-gold) / 0.5)',
            transform: 'translateZ(25px)',
          }}
          initial={{ scale: 0, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ delay: 0.8, duration: 0.6 }}
        >
          <motion.div
            className="absolute inset-1 rounded-full"
            style={{
              background: 'radial-gradient(circle, hsl(var(--ojas-gold-light)) 0%, hsl(var(--ojas-gold)) 100%)',
            }}
            animate={{
              scale: [1, 1.15, 1],
              opacity: [0.9, 1, 0.9],
            }}
            transition={{
              duration: 2.5,
              repeat: Infinity,
              ease: 'easeInOut',
            }}
          />
        </motion.div>
      </motion.div>

      {/* Sparkle Effects - Consistent positions */}
      {sparkles.map((sparkle, i) => (
        <motion.div
          key={`sparkle-${i}`}
          className="absolute w-1.5 h-1.5 rounded-full"
          style={{
            left: sparkle.left,
            top: sparkle.top,
            background: 'hsl(var(--ojas-gold-light))',
            boxShadow: '0 0 6px hsl(var(--ojas-gold-light))',
          }}
          animate={{
            scale: [0, 1, 0],
            opacity: [0, 0.8, 0],
          }}
          transition={{
            duration: 2.5,
            repeat: Infinity,
            delay: sparkle.delay,
            ease: 'easeInOut',
          }}
        />
      ))}
    </div>
  );
};
