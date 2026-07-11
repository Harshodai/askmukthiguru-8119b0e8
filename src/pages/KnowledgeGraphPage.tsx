import { KGConceptMap } from '@/components/kg/KGConceptMap';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

export default function KnowledgeGraphPage() {
  const [params] = useSearchParams();
  const initialQuery = params.get('q') ?? '';
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border/30">
        <div className="max-w-4xl mx-auto px-4 py-6">
          <h1 className="font-serif text-2xl text-foreground">Knowledge Graph</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Explore how the sacred concepts of the Ekam teachings connect.
          </p>
        </div>
      </header>
      <main className="py-6">
        <KGConceptMap initialQuery={initialQuery} />
      </main>
    </div>
  );
}