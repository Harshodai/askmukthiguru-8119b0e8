import { motion } from 'framer-motion';

export interface ProgressRingProps {
  currentStep: number;
  totalSteps: number;
  /** 0–1 progress within the current step */
  stepProgress: number;
  size?: number;
  radius?: number;
  strokeWidth?: number;
  centerContent?: React.ReactNode;
}

export const ProgressRing = ({
  currentStep,
  totalSteps,
  stepProgress,
  size = 144,
  radius = 54,
  strokeWidth = 4,
  centerContent,
}: ProgressRingProps) => {
  const overallProgress = (currentStep + stepProgress) / totalSteps;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - overallProgress);

  return (
    <div
      className="relative flex items-center justify-center"
      style={{ width: size, height: size }}
    >
      {/* Background ring */}
      <svg
        className="absolute inset-0 w-full h-full -rotate-90"
        viewBox={`0 0 ${size} ${size}`}
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          className="text-muted-foreground/15"
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="url(#goldGrad)"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          animate={{ strokeDashoffset: dashOffset }}
          transition={{ duration: 0.6, ease: 'easeInOut' }}
        />
        <defs>
          <linearGradient id="goldGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="hsl(var(--ojas))" />
            <stop offset="100%" stopColor="hsl(var(--ojas-light))" />
          </linearGradient>
        </defs>
      </svg>

      {/* Step dots around the ring */}
      {Array.from({ length: totalSteps }).map((_, i) => {
        const angle = (i / totalSteps) * 360 - 90;
        const rad = (angle * Math.PI) / 180;
        const x = size / 2 + radius * Math.cos(rad);
        const y = size / 2 + radius * Math.sin(rad);
        const done = i < currentStep;
        const active = i === currentStep;
        return (
          <svg
            key={i}
            className="absolute inset-0 w-full h-full"
            viewBox={`0 0 ${size} ${size}`}
          >
            <circle
              cx={x}
              cy={y}
              r={active ? 5 : 3.5}
              className={done ? 'fill-ojas' : active ? 'fill-ojas-light' : 'fill-muted-foreground/30'}
            />
          </svg>
        );
      })}

      {/* Center content */}
      <div className="relative z-10">{centerContent}</div>
    </div>
  );
};
