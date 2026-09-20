import { PublicShell } from '@/components/layout/PublicShell';
import { usePageMeta } from '@/hooks/usePageMeta';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { buildCanonical } from '@/lib/domain';
import { useTranslation } from 'react-i18next';
import { getAiSpiritualCompanionContent } from '@/lib/guidesContent';

const AiSpiritualCompanionPage = () => {
  const { t } = useTranslation();
  const content = getAiSpiritualCompanionContent(t);
  const canonicalUrl = buildCanonical('/guides/ai-spiritual-companion');

  usePageMeta({
    title: content.meta.title,
    description: content.meta.description,
    canonical: canonicalUrl,
    ogType: 'article',
    jsonLd: {
      '@context': 'https://schema.org',
      '@graph': [
        {
          '@type': 'Article',
          headline: content.meta.articleHeadline,
          description: content.meta.articleDescription,
          author: { '@type': 'Organization', name: 'AskMukthiGuru' },
          mainEntityOfPage: canonicalUrl,
          keywords: 'AI spiritual guide, AI-guided meditation, Beautiful State, spiritual growth, yogic wisdom',
        },
        {
          '@type': 'FAQPage',
          mainEntity: content.faqs.items.map((f) => ({
            '@type': 'Question',
            name: f.q,
            acceptedAnswer: { '@type': 'Answer', text: f.a },
          })),
        },
      ],
    },
  });

  return (
    <PublicShell title={content.meta.publicShellTitle}>
      <article className="mx-auto max-w-3xl px-4 py-10 space-y-8">
        <header className="space-y-3">
          <h1 className="text-3xl sm:text-4xl font-serif font-semibold text-foreground">
            {content.header.title}
          </h1>
          <p className="text-muted-foreground">
            {content.header.subtitle}
          </p>
        </header>

        {content.sections.map((s) => (
          <section key={s.title} className="space-y-2">
            <h2 className="text-xl font-semibold text-foreground">{s.title}</h2>
            <p className="text-foreground/90 leading-relaxed">{s.body}</p>
          </section>
        ))}

        <section className="space-y-4">
          <h2 className="text-xl font-semibold text-foreground">
            {content.steps.heading}
          </h2>
          <ol className="space-y-4">
            {content.steps.items.map((s) => (
              <li key={s.n} className="flex gap-4">
                <span className="flex-shrink-0 w-8 h-8 rounded-full bg-ojas/10 text-ojas font-semibold flex items-center justify-center">
                  {s.n}
                </span>
                <div className="space-y-1">
                  <h3 className="font-semibold text-foreground">{s.title}</h3>
                  <p className="text-foreground/90 leading-relaxed">{s.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold text-foreground">
            {content.breathwork.heading}
          </h2>
          <p className="text-foreground/90 leading-relaxed">
            {content.breathwork.body}
          </p>
        </section>

        <section className="space-y-4">
          <h2 className="text-xl font-semibold text-foreground">{content.faqs.heading}</h2>
          <dl className="space-y-4">
            {content.faqs.items.map((f) => (
              <div key={f.q} className="space-y-1">
                <dt className="font-semibold text-foreground">{f.q}</dt>
                <dd className="text-foreground/90 leading-relaxed">{f.a}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="space-y-3 rounded-lg border border-border/60 bg-card/60 p-6">
          <h2 className="text-xl font-semibold text-foreground">{content.cta.heading}</h2>
          <p className="text-foreground/90 leading-relaxed">
            {content.cta.body}
          </p>
          <div className="flex flex-wrap gap-2 pt-2">
            <Button asChild>
              <Link to="/chat">{content.cta.chatButton}</Link>
            </Button>
            <Button asChild variant="outline">
              <Link to="/practices/serene-mind">{content.cta.practiceButton}</Link>
            </Button>
            <Button asChild variant="ghost">
              <Link to="/practices">{content.cta.exploreButton}</Link>
            </Button>
          </div>
        </section>
      </article>
    </PublicShell>
  );
};

export default AiSpiritualCompanionPage;
