import { PublicShell } from '@/components/layout/PublicShell';
import { usePageMeta } from '@/hooks/usePageMeta';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { buildCanonical } from '@/lib/domain';

const SpiritGuidesPage = () => {
  const canonicalUrl = buildCanonical('/guides/spirit-guides');
  usePageMeta({
    title: 'Guide under review — AskMukthiGuru',
    description:
      'This guide is under editorial review while AskMukthiGuru verifies its source support.',
    canonical: canonicalUrl,
    ogType: 'article',
    jsonLd: {
      '@context': 'https://schema.org',
      '@type': 'Article',
      headline: 'Guide under review',
      author: { '@type': 'Organization', name: 'AskMukthiGuru' },
      mainEntityOfPage: canonicalUrl,
    },
  });

  return (
    <PublicShell title="Guide under review">
      <article className="mx-auto max-w-3xl px-4 py-10 space-y-8">
        <header className="space-y-3">
          <h1 className="text-3xl sm:text-4xl font-serif font-semibold text-foreground">
            This guide is under review
          </h1>
          <p className="text-muted-foreground">
            We removed this page’s earlier claims because they were not linked to verified source material.
            We will only publish it again after editorial and source review.
          </p>
        </header>

        <section className="space-y-3 rounded-lg border border-border/60 bg-card/60 p-6">
          <h2 className="text-xl font-semibold text-foreground">Explore verified material</h2>
          <p className="text-foreground/90 leading-relaxed">
            Ask a question in chat to see source-linked material when it is available, or explore a
            practice without treating it as medical, mental-health, or supernatural advice.
          </p>
          <div className="flex flex-wrap gap-2 pt-2">
            <Button asChild>
              <Link to="/chat">Begin a conversation</Link>
            </Button>
            <Button asChild variant="outline">
              <Link to="/practices/serene-mind">Try Serene Mind</Link>
            </Button>
          </div>
        </section>
      </article>
    </PublicShell>
  );
};

export default SpiritGuidesPage;
