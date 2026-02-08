import { motion } from 'framer-motion';

interface LotusFlower3DProps {
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

export const LotusFlower3D = ({ className = '', size = 'md' }: LotusFlower3DProps) => {
  const sizeClasses = {
    sm: 'w-32 h-32',
    md: 'w-48 h-48',
    lg: 'w-64 h-64',
  };

  const petalColors = {
    outer: 'from-ojas/40 to-ojas-light/60',
    middle: 'from-ojas/50 to-ojas-light/70',
    inner: 'from-ojas/60 to-ojas-light/80',
  };

  // Generate petals for each layer
  const createPetalLayer = (
    petalCount: number,
    layerIndex: number,
    rotateX: number,
    translateZ: number,
    scale: number,
    colorClass: string
  ) => {
    return Array.from({ length: petalCount }).map((_, i) => {
      const rotation = (360 / petalCount) * i + layerIndex * 15;
      return (
        <motion.div
          key={`layer-${layerIndex}-petal-${i}`}
          className="absolute left-1/2 bottom-1/2 origin-bottom"
          style={{
            width: `${40 * scale}%`,
            height: `${50 * scale}%`,
            transform: `rotateY(${rotation}deg) rotateX(${rotateX}deg) translateZ(${translateZ}px) translateX(-50%)`,
            transformStyle: 'preserve-3d',
          }}
          initial={{ rotateX: 80, opacity: 0 }}
          animate={{ 
            rotateX: rotateX,
            opacity: 1,
          }}
          transition={{
            duration: 1.5,
            delay: 0.1 * i + 0.3 * layerIndex,
            ease: 'easeOut',
          }}
        >
          <motion.div
            className={`w-full h-full bg-gradient-to-t ${colorClass} rounded-t-full shadow-lg`}
            style={{
              backfaceVisibility: 'hidden',
              boxShadow: '0 0 20px hsl(var(--ojas-gold) / 0.3)',
            }}
            animate={{
              rotateY: [-2, 2, -2],
              rotateX: [0, 2, 0],
            }}
            transition={{
              duration: 4 + Math.random() * 2,
              repeat: Infinity,
              ease: 'easeInOut',
              delay: Math.random() * 2,
            }}
          />
        </motion.div>
      );
    });
  };

  return (
    <div className={`relative ${sizeClasses[size]} ${className}`} style={{ perspective: '1000px' }}>
      {/* Glow Effect Behind Lotus */}
      <motion.div
        className="absolute inset-0 rounded-full bg-gradient-radial from-ojas/30 via-ojas-light/20 to-transparent blur-xl"
        animate={{
          scale: [1, 1.1, 1],
          opacity: [0.5, 0.7, 0.5],
        }}
        transition={{
          duration: 4,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
      />

      {/* Main Lotus Container */}
      <motion.div
        className="absolute inset-0"
        style={{ 
          transformStyle: 'preserve-3d',
          transform: 'rotateX(15deg)',
        }}
        initial={{ rotateX: 45, scale: 0.5, opacity: 0 }}
        animate={{ rotateX: 15, scale: 1, opacity: 1 }}
        transition={{ duration: 1.5, ease: 'easeOut' }}
      >
        {/* Outer Layer - 8 petals */}
        <div 
          className="absolute inset-0" 
          style={{ transformStyle: 'preserve-3d' }}
        >
          {createPetalLayer(8, 0, 25, 10, 1, petalColors.outer)}
        </div>

        {/* Middle Layer - 8 petals */}
        <div 
          className="absolute inset-0" 
          style={{ transformStyle: 'preserve-3d' }}
        >
          {createPetalLayer(8, 1, 35, 20, 0.85, petalColors.middle)}
        </div>

        {/* Inner Layer - 6 petals */}
        <div 
          className="absolute inset-0" 
          style={{ transformStyle: 'preserve-3d' }}
        >
          {createPetalLayer(6, 2, 50, 30, 0.7, petalColors.inner)}
        </div>

        {/* Center of Lotus */}
        <motion.div
          className="absolute left-1/2 top-1/2 w-1/4 h-1/4 -translate-x-1/2 -translate-y-1/2 rounded-full"
          style={{
            background: 'radial-gradient(circle, hsl(var(--ojas-gold)) 0%, hsl(var(--ojas-gold-light)) 50%, transparent 100%)',
            boxShadow: '0 0 30px hsl(var(--ojas-gold) / 0.6), 0 0 60px hsl(var(--ojas-gold) / 0.3)',
            transform: 'translateZ(40px)',
          }}
          initial={{ scale: 0, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ delay: 1, duration: 0.8 }}
        >
          {/* Inner glow pulse */}
          <motion.div
            className="absolute inset-0 rounded-full bg-ojas-light"
            animate={{
              scale: [1, 1.2, 1],
              opacity: [0.8, 1, 0.8],
            }}
            transition={{
              duration: 2,
              repeat: Infinity,
              ease: 'easeInOut',
            }}
          />
        </motion.div>
      </motion.div>

      {/* Sparkle Effects */}
      {[...Array(5)].map((_, i) => (
        <motion.div
          key={`sparkle-${i}`}
          className="absolute w-1 h-1 bg-ojas-light rounded-full"
          style={{
            left: `${30 + Math.random() * 40}%`,
            top: `${20 + Math.random() * 40}%`,
          }}
          animate={{
            scale: [0, 1, 0],
            opacity: [0, 1, 0],
          }}
          transition={{
            duration: 2,
            repeat: Infinity,
            delay: i * 0.5,
            ease: 'easeInOut',
          }}
        />
      ))}
    </div>
  );
};
