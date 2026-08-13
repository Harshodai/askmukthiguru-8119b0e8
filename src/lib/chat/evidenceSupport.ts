/**
 * User-facing evidence support labels. The raw verifier score is intentionally
 * never rendered: it is a model signal, not a probability or quality promise.
 */
export type EvidenceSupport = {
  label: 'Teaching-supported' | 'Partially supported' | 'Limited support';
  description: string;
};

export function evidenceSupport(score: number | null | undefined): EvidenceSupport {
  if (typeof score !== 'number' || !Number.isFinite(score) || score < 5) {
    return {
      label: 'Limited support',
      description: 'No or limited supporting context was available',
    };
  }
  if (score < 8) {
    return {
      label: 'Partially supported',
      description: 'Some supporting context was available',
    };
  }
  return {
    label: 'Teaching-supported',
    description: 'Strong retrieved and verified support',
  };
}
