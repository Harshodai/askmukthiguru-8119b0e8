import { ExternalLink } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { memorySourceHref, memorySourceLabel, type MemorySourceRef } from '@/lib/memorySource';

interface MemorySourceLinkProps {
  source?: MemorySourceRef | null;
  className?: string;
}

/**
 * Link back to where a memory came from, or an honest "Source unavailable".
 * It never builds a link from anything the backend did not prove.
 */
export function MemorySourceLink({ source, className }: MemorySourceLinkProps) {
  const { t } = useTranslation();
  const location = useLocation();
  const href = memorySourceHref(source, `${location.pathname}${location.search}`);

  if (!href) {
    return (
      <span data-testid="memory-source-unavailable" className={cn('text-xs text-muted-foreground', className)}>
        {t('memory.sourceUnavailable', 'Source unavailable')}
      </span>
    );
  }

  const isNotebook = source?.kind === 'notebook';
  return (
    <Link
      to={href}
      data-testid="memory-source-link"
      className={cn(
        'inline-flex min-h-11 items-center gap-1.5 rounded-md text-xs font-medium text-foreground underline decoration-primary decoration-2 underline-offset-4 hover:text-foreground/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/50',
        className,
      )}
    >
      <span>
        {isNotebook
          ? t('memory.openNotebook', memorySourceLabel(source))
          : t('memory.openConversation', memorySourceLabel(source))}
      </span>
      <ExternalLink className="h-3 w-3" aria-hidden="true" />
    </Link>
  );
}
