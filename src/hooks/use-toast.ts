/**
 * Legacy `useToast` compatibility shim.
 *
 * Historically this app had two parallel toast systems: a hand-rolled Radix
 * reducer here (`useToast`) rendered by `@/components/ui/toaster`, and
 * Sonner rendered by `@/components/ui/sonner`. The Radix path had ~20
 * callsites and its own visual language, which meant "world-class"
 * notifications needed to be built and maintained twice.
 *
 * This shim keeps every existing `useToast()` / `toast({ title, description,
 * variant })` callsite working unchanged, but forwards to Sonner internally
 * so there is a single toast surface to design — the Warm Sacred theme in
 * `@/components/ui/sonner`.
 */
import * as React from 'react';
import { toast as sonnerToast, type ExternalToast } from 'sonner';

type Variant = 'default' | 'destructive' | 'success' | 'warning' | 'info';

interface LegacyToastArgs {
  id?: string | number;
  title?: React.ReactNode;
  description?: React.ReactNode;
  variant?: Variant;
  duration?: number;
  action?: React.ReactNode;
}

const renderNode = (node: React.ReactNode): string | React.ReactNode => {
  // Sonner accepts strings or ReactNode for title/description; pass through.
  return node ?? '';
};

function toast(args: LegacyToastArgs) {
  const { title, description, variant = 'default', duration, id } = args;

  const opts: ExternalToast = {
    description: description ? renderNode(description) : undefined,
    duration,
    id,
  };

  const label = renderNode(title) || '';

  let toastId: string | number;
  switch (variant) {
    case 'destructive':
      toastId = sonnerToast.error(label as string, opts);
      break;
    case 'success':
      toastId = sonnerToast.success(label as string, opts);
      break;
    case 'warning':
      toastId = sonnerToast.warning(label as string, opts);
      break;
    case 'info':
      toastId = sonnerToast.info(label as string, opts);
      break;
    default:
      toastId = sonnerToast(label as string, opts);
  }

  return {
    id: String(toastId),
    dismiss: () => sonnerToast.dismiss(toastId),
    update: (next: LegacyToastArgs) => toast({ ...next, id: toastId }),
  };
}

function useToast() {
  return React.useMemo(
    () => ({
      toast,
      toasts: [] as unknown[],
      dismiss: (id?: string | number) => sonnerToast.dismiss(id),
    }),
    [],
  );
}

export { useToast, toast };
