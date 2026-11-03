import * as React from 'react';
import { cn } from '@/lib/utils';

interface EkamGoldenOrbProps extends React.SVGProps<SVGSVGElement> {
  className?: string;
  size?: number | string;
}

/**
 * EkamGoldenOrb
 *
 * The sacred Golden Orb (Svarna Golakam / Hiranyagarbha) of Ekam,
 * representing universal divine consciousness, oneness, and the Beautiful State
 * as taught by Sri Preethaji & Sri Krishnaji.
 */
export const EkamGoldenOrb: React.FC<EkamGoldenOrbProps> = ({
  className,
  size = 20,
  ...props
}) => {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn('shrink-0 select-none', className)}
      aria-hidden="true"
      {...props}
    >
      {/* Outer subtle radiance aura */}
      <circle
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="1"
        strokeDasharray="1.5 2"
        opacity="0.55"
      />

      {/* Middle concentric ring of oneness */}
      <circle
        cx="12"
        cy="12"
        r="7.5"
        stroke="currentColor"
        strokeWidth="1.25"
        opacity="0.8"
      />

      {/* 8 Cardinal & Ordinal Rays of Divine Grace */}
      <line x1="12" y1="0.75" x2="12" y2="3.25" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="12" y1="20.75" x2="12" y2="23.25" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="0.75" y1="12" x2="3.25" y2="12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="20.75" y1="12" x2="23.25" y2="12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />

      <line x1="4.05" y1="4.05" x2="5.8" y2="5.8" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" opacity="0.8" />
      <line x1="18.2" y1="18.2" x2="19.95" y2="19.95" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" opacity="0.8" />
      <line x1="4.05" y1="19.95" x2="5.8" y2="18.2" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" opacity="0.8" />
      <line x1="18.2" y1="5.8" x2="19.95" y2="4.05" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" opacity="0.8" />

      {/* Inner Golden Orb Sphere */}
      <circle cx="12" cy="12" r="4.5" fill="currentColor" />

      {/* Central Bindu / Core of Pure Consciousness */}
      <circle cx="12" cy="12" r="1.5" fill="#FFFDF0" opacity="0.95" />
    </svg>
  );
};
