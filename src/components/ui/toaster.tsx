/**
 * Legacy Radix `<Toaster />` — kept as a no-op mount point so `App.tsx` and
 * historical imports continue to type-check. The real toast rendering lives
 * in `@/components/ui/sonner` (Warm Sacred theme), which every callsite —
 * including the legacy `useToast()` hook — now routes through.
 */
export function Toaster() {
  return null;
}
