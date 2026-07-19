import { KGConceptMap } from '@/components/kg/KGConceptMap';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

// Public — Wisdom Map is a discovery surface, no auth gate.
// If we need to gate later, add useRequireAuth back.
export default function KnowledgeGraphPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const initialQuery = params.get('q') ?? '';

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border/30">
        <div className="max-w-5xl mx-auto px-4 py-6">
          <h1 className="font-sacred text-3xl text-foreground">{t('kg.title', 'Wisdom Map')}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {t('kg.subtitle', 'Explore how the sacred concepts of the Ekam teachings connect.')}
          </p>
        </div>
      </header>
      <main className="py-6">
        <KGConceptMap initialQuery={initialQuery} />
      </main>
    </div>
  );
}
