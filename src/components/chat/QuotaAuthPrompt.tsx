import { Button } from '@/components/ui/button';
import { LogIn } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

/**
 * Soft auth prompt shown above the composer when an anonymous session
 * exhausts its free-message quota. Uses the same visual language as the
 * chat error banner but keeps the input disabled state in the parent.
 */
export const QuotaAuthPrompt = ({ remaining, totalLimit }: { remaining?: number; totalLimit?: number }) => {
  const navigate = useNavigate();
  return (
    <div className="mx-3 sm:mx-5 mb-3 rounded-2xl border border-ojas/20 bg-gradient-to-r from-ojas/10 to-background p-4 shadow-sm flex flex-col sm:flex-row items-start sm:items-center gap-3">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground">
          Free message limit reached
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">
          Sign in to continue the conversation{totalLimit !== undefined && remaining !== undefined ? ` (${totalLimit - remaining} of ${totalLimit} used)` : ''}.
        </p>
      </div>
      <Button
        type="button"
        size="sm"
        onClick={() => navigate('/auth')}
        className="bg-ojas hover:bg-ojas-light text-primary-foreground gap-2 shrink-0"
      >
        <LogIn className="w-4 h-4" />
        Sign in
      </Button>
    </div>
  );
};

export default QuotaAuthPrompt;
