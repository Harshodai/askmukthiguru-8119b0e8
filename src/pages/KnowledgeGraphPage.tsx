import { KGConceptMap } from '@/components/kg/KGConceptMap';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { X, Sparkles } from 'lucide-react';

// Public — Wisdom Map is a discovery surface, no auth gate.
export default function KnowledgeGraphPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const initialQuery = params.get('q') ?? '';

  const handleClose = () => {
    if (window.history.length > 1) navigate(-1);
    else navigate('/chat');
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-background via-background to-primary/5 relative">
      {/* Ambient orbs */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-32 -left-32 w-96 h-96 rounded-full bg-primary/10 blur-3xl" />
        <div className="absolute -top-20 right-0 w-80 h-80 rounded-full bg-amber-400/10 blur-3xl" />
      </div>

      <header className="relative border-b border-border/40 backdrop-blur-md bg-background/60 sticky top-0 z-20">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-5 flex items-start justify-between gap-4">
          <div className="flex items-start gap-3 min-w-0">
            <div className="hidden sm:flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-primary/20 to-amber-400/20 border border-primary/20 shadow-sm">
              <Sparkles className="w-5 h-5 text-primary" />
            </div>
            <div className="min-w-0">
              <h1 className="font-sacred text-2xl sm:text-3xl text-foreground leading-tight truncate">
                {t('kg.title', 'Wisdom Map')}
              </h1>
              <p className="text-xs sm:text-sm text-muted-foreground mt-1 max-w-xl">
                {t('kg.subtitle', 'Explore how the sacred concepts of the Ekam teachings connect.')}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={handleClose}
            aria-label={t('common.close', 'Close')}
            className="shrink-0 inline-flex items-center justify-center h-10 w-10 rounded-full border border-border/60 bg-background/80 text-muted-foreground hover:text-foreground hover:bg-background hover:border-border transition-all shadow-sm hover:shadow focus:outline-none focus:ring-2 focus:ring-primary/40"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </header>

      <main className="relative py-4 sm:py-6">
        <KGConceptMap initialQuery={initialQuery} />
      </main>
    </div>
  );
}
