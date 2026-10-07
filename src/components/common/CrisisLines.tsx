import type { CrisisLine } from '@/lib/crisisHelplines';
import { cn } from '@/lib/utils';

interface CrisisLinesProps {
  lines: readonly CrisisLine[];
  className?: string;
}

/** Tap-to-call helpline list. Numbers come from `@/lib/crisisHelplines`. */
export const CrisisLines = ({ lines, className }: CrisisLinesProps) => (
  <ul className={cn('space-y-1', className)}>
    {lines.map((line) => (
      <li key={line.registryName}>
        <span className="font-medium text-foreground">{line.label}: </span>
        <a
          href={`tel:${line.tel}`}
          className="font-semibold text-foreground underline underline-offset-2 hover:no-underline"
          aria-label={`Call ${line.label} at ${line.display}`}
        >
          {line.display}
        </a>
        <span className="text-muted-foreground"> ({line.hours})</span>
      </li>
    ))}
  </ul>
);
