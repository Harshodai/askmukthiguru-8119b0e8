import { motion } from 'framer-motion';

interface MeditationProgressIndicatorProps {
  currentStep: number;
  totalSteps: number;
  /** 0–1 progress within the current step */
  stepProgress: number;
}

/**
 * Two-palm "hand-in-hand" progress ring.
 * Renders as a circular progress ring with step dots.
 */
export const MeditationProgressIndicator = ({
  currentStep,
  totalSteps,
  stepProgress,
}: MeditationProgressIndicatorProps) => {
  const overallProgress = (currentStep + stepProgress) / totalSteps;
  const circumference = 2 * Math.PI * 54; // radius=54
  const dashOffset = circumference * (1 - overallProgress);

  return (
    <div className="relative w-36 h-36 flex items-center justify-center">
      {/* Background ring */}
      <svg className="absolute inset-0 w-full h-full -rotate-90" viewBox="0 0 120 120">
        <circle
          cx="60" cy="60" r="54"
          fill="none"
          stroke="currentColor"
          strokeWidth="4"
          className="text-muted-foreground/15"
        />
        <motion.circle
          cx="60" cy="60" r="54"
          fill="none"
          stroke="url(#goldGrad)"
          strokeWidth="4"
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
        const x = 60 + 54 * Math.cos(rad);
        const y = 60 + 54 * Math.sin(rad);
        const done = i < currentStep;
        const active = i === currentStep;
        return (
          <svg key={i} className="absolute inset-0 w-full h-full" viewBox="0 0 120 120">
            <circle
              cx={x} cy={y} r={active ? 5 : 3.5}
              className={done ? 'fill-ojas' : active ? 'fill-ojas-light' : 'fill-muted-foreground/30'}
            />
          </svg>
        );
      })}

      {/* Center content */}
      <div className="relative z-10 text-center">
        <p className="text-3xl font-semibold text-ojas">{currentStep + 1}</p>
        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">of {totalSteps}</p>
      </div>
    </div>
  );
};
