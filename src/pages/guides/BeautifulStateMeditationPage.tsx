import { PublicShell } from '@/components/layout/PublicShell';
import { usePageMeta } from '@/hooks/usePageMeta';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { buildCanonical } from '@/lib/domain';
import { useTranslation } from 'react-i18next';
import { getBeautifulStateMeditationContent } from '@/lib/guidesContent';

const BeautifulStateMeditationPage = () => {
  const { t } = useTranslation();
  const content = getBeautifulStateMeditationContent(t);
  const canonicalUrl = buildCanonical('/guides/beautiful-state-meditation');

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
          keywords: 'beautiful state meditation, how to enter beautiful state, Preethaji Krishnaji, spiritual meditation',
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
      <article className="mx-auto max-w-3xl px-4 py-10 space-y-8 text-foreground/90 leading-relaxed">
        <header className="space-y-3">
          <h1 className="text-3xl sm:text-4xl font-serif font-semibold text-foreground">
            {content.header.title}
          </h1>
          <p className="text-muted-foreground">
            {content.header.subtitle}
          </p>
        </header>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">{content.whatIs.heading}</h2>
          <p>{content.whatIs.body}</p>
          <h3 className="text-lg font-semibold text-foreground pt-2">{content.whatIs.vsTitle}</h3>
          <p>{content.whatIs.vsBody}</p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">{content.practice.heading}</h2>
          {content.practice.steps.map((step, idx) => (
            <div key={idx} className={idx > 0 ? 'space-y-1 pt-2' : 'space-y-1'}>
              <h3 className="text-lg font-semibold text-foreground">{step.title}</h3>
              <p>{step.body}</p>
            </div>
          ))}
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">{content.threeMinute.heading}</h2>
          <ul className="list-disc pl-6 space-y-2">
            <li>
              <strong>{content.threeMinute.min1Label}</strong> {content.threeMinute.min1Body}
            </li>
            <li>
              <strong>{content.threeMinute.min2Label}</strong> {content.threeMinute.min2Body}
            </li>
            <li>
              <strong>{content.threeMinute.min3Label}</strong> {content.threeMinute.min3Body}
            </li>
          </ul>
          <p>{content.threeMinute.footer}</p>
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold text-foreground">{content.harder.heading}</h2>
          <p>{content.harder.body}</p>
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold text-foreground">{content.dailyLife.heading}</h2>
          <p>
            {content.dailyLife.part1}
            <Link to="/practices" className="text-ojas underline">
              {content.dailyLife.browsePracticesLink}
            </Link>
            {content.dailyLife.part2}
            <Link to="/guides/ai-spiritual-companion" className="text-ojas underline">
              {content.dailyLife.aiCompanionLink}
            </Link>
            {content.dailyLife.part3}
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
          <p className="text-foreground/90 leading-relaxed">{content.cta.body}</p>
          <div className="flex flex-wrap gap-2 pt-2">
            <Button asChild>
              <Link to="/chat">{content.cta.startChat}</Link>
            </Button>
            <Button asChild variant="outline">
              <Link to="/guides/serene-mind-practice">{content.cta.learnSereneMind}</Link>
            </Button>
          </div>
        </section>
      </article>
    </PublicShell>
  );
};

export default BeautifulStateMeditationPage;
