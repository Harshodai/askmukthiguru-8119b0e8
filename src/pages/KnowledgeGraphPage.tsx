import { KGConceptMap } from '@/components/kg/KGConceptMap';
import { useSearchParams, useNavigate, useLocation } from 'react-router-dom';
import { returnToOrigin } from '@/lib/workspaceNavigation';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, Sparkles } from 'lucide-react';

// Public — Wisdom Map is a discovery surface, no auth gate.
export default function KnowledgeGraphPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const initialQuery = params.get('q') ?? '';

  const handleClose = () => {
    returnToOrigin(navigate, location);
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-background via-background/95 to-primary/5 relative">
      {/* Sacred Ambient Background Glow */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-96 bg-gradient-to-b from-ojas/10 via-ojas/5 to-transparent blur-3xl opacity-60"
        aria-hidden="true"
      />

      <header className="relative border-b border-border/40 backdrop-blur-md bg-background/70 sticky top-0 z-20 shadow-sm">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-start gap-3 min-w-0">
            <div className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-ojas/25 bg-ojas/10 text-ojas shadow-inner">
              <Sparkles className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="font-sacred text-2xl sm:text-3xl text-foreground leading-tight truncate">
                  {t('kg.title', 'Wisdom Map')}
                </h1>
                <span className="hidden sm:inline-flex rounded-full border border-ojas/20 bg-ojas/5 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-ojas">
                  {t('kg.consciousnessGraph', 'Consciousness Graph')}
                </span>
              </div>
              <p className="text-xs sm:text-sm text-muted-foreground mt-0.5 max-w-xl">
                {t(
                  'kg.subtitle',
                  'Explore how your personal inquiries, inner states, and sacred practices weave into the Ekam teachings.',
                )}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 self-end sm:self-center">
            <button
              type="button"
              onClick={handleClose}
              aria-label={t('layout.backToChat', 'Back to Chat')}
              title={t('layout.backToChat', 'Back to Chat')}
              className="shrink-0 inline-flex items-center gap-2 min-h-10 rounded-xl border border-border/60 bg-background/90 px-3.5 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-background hover:border-border transition-all shadow-sm hover:shadow focus:outline-none focus:ring-2 focus:ring-primary/40"
            >
              <ArrowLeft className="w-4 h-4" aria-hidden="true" />
              <span>{t('layout.backToChat', 'Back to Chat')}</span>
            </button>
          </div>
        </div>
      </header>

      <main className="relative py-4 sm:py-6">
        <KGConceptMap initialQuery={initialQuery} />
      </main>
    </div>
  );
}
