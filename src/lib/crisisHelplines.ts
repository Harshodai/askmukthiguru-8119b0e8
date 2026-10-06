/**
 * Crisis helplines shown in frontend copy (first-run safety notice, landing
 * crisis dialog).
 *
 * config/helplines.yaml is the single source of truth for every number; this
 * is a deliberately small mirror of it, because the browser bundle cannot read
 * the YAML at runtime. src/test/crisisHelplines.test.ts fails if any entry
 * here drifts from the registry, so a number is never changed in one place
 * only. Order matters: the line the owner has call-verified (Tele-MANAS) and
 * the national emergency number come first; both answer 24/7 at no cost.
 */
export interface CrisisLine {
  /** Exact `name` of the matching entry in config/helplines.yaml. */
  registryName: string;
  /** Short label shown to the seeker. */
  label: string;
  /** Number as displayed. Must appear in the registry entry's `contact`. */
  display: string;
  /** Digits (and leading +) for the tel: link. */
  tel: string;
  /** Exact `hours` of the registry entry. */
  hours: string;
}

export const INDIA_CRISIS_LINES: readonly CrisisLine[] = [
  {
    registryName: 'Tele-MANAS (National Mental Health Helpline)',
    label: 'Tele-MANAS',
    display: '14416',
    tel: '14416',
    hours: '24/7, free',
  },
  {
    registryName: 'National Emergency Services',
    label: 'Emergency',
    display: '112',
    tel: '112',
    hours: '24/7',
  },
  {
    registryName: 'Vandrevala Foundation',
    label: 'Vandrevala Foundation',
    display: '+91 9999 666 555',
    tel: '+919999666555',
    hours: '24/7',
  },
];

export const US_CRISIS_LINES: readonly CrisisLine[] = [
  {
    registryName: '988 Suicide & Crisis Lifeline',
    label: '988 Suicide & Crisis Lifeline',
    display: '988',
    tel: '988',
    hours: '24/7',
  },
];
