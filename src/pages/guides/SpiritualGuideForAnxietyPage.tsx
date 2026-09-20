import { PublicShell } from '@/components/layout/PublicShell';
import { usePageMeta } from '@/hooks/usePageMeta';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { buildCanonical } from '@/lib/domain';
import { useTranslation } from 'react-i18next';
import { getSpiritualGuideForAnxietyContent } from '@/lib/guidesContent';

const SpiritualGuideForAnxietyPage = () => {
  const { t } = useTranslation();
  const content = getSpiritualGuideForAnxietyContent(t);
  const canonicalUrl = buildCanonical('/guides/spiritual-guide-for-anxiety');

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
          keywords: 'AI spiritual guide for anxiety, spiritual help for anxiety, meditation for anxiety spiritual',
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
          <h2 className="text-xl font-semibold text-foreground">{content.notInHead.heading}</h2>
          <p>
            {content.notInHead.part1}
            <Link to="/guides/self-centric-thinking" className="text-ojas underline">
              {content.notInHead.selfCentricLink}
            </Link>
            {content.notInHead.part2}
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">{content.notInHead.sufferingStateHeading}</h3>
          <p>{content.notInHead.sufferingStateBody}</p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">{content.howAiHelps.heading}</h2>
          <p>{content.howAiHelps.body1}</p>
          <h3 className="text-lg font-semibold text-foreground pt-2">{content.howAiHelps.practicalHeading}</h3>
          <p>{content.howAiHelps.body2}</p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">{content.approach.heading}</h2>
          <div className="space-y-1">
            <h3 className="text-lg font-semibold text-foreground">{content.approach.steps[0].title}</h3>
            <p>{content.approach.steps[0].body}</p>
          </div>
          <div className="space-y-1 pt-2">
            <h3 className="text-lg font-semibold text-foreground">{content.approach.steps[1].title}</h3>
            <p>{content.approach.steps[1].body}</p>
          </div>
          <div className="space-y-1 pt-2">
            <h3 className="text-lg font-semibold text-foreground">{content.approach.steps[2].title}</h3>
            <p>
              {content.approach.steps[2].part1}
              <Link to="/guides/serene-mind-practice" className="text-ojas underline">
                {content.approach.steps[2].sereneMindLink}
              </Link>
              {content.approach.steps[2].part2}
            </p>
          </div>
          <div className="space-y-1 pt-2">
            <h3 className="text-lg font-semibold text-foreground">{content.approach.steps[3].title}</h3>
            <p>{content.approach.steps[3].body}</p>
          </div>
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold text-foreground">{content.movingToward.heading}</h2>
          <p>
            {content.movingToward.part1}
            <Link to="/guides/beautiful-state-meditation" className="text-ojas underline">
              {content.movingToward.beautifulStateLink}
            </Link>
            {content.movingToward.part2}
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold text-foreground">{content.dailyPractice.heading}</h2>
          <p>
            {content.dailyPractice.part1}
            <Link to="/practices" className="text-ojas underline">
              {content.dailyPractice.browsePracticesLink}
            </Link>
            {content.dailyPractice.part2}
          </p>
        </section>

        <section className="space-y-4">
          <h2 className="text-xl font-semibold text-foreground">{content.faqs.heading}</h2>
          <dl className="space-y-4">
            {content.faqs.items.map((f) => (
              <div key={f.q} className="space-y-1">
                <dt className="font-semibold text-foreground">{f.q}</dt>
                <dd>{f.a}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="space-y-3 rounded-lg border border-border/60 bg-card/60 p-6">
          <h2 className="text-xl font-semibold text-foreground">{content.cta.heading}</h2>
          <p>{content.cta.body}</p>
          <div className="flex flex-wrap gap-2 pt-2">
            <Button asChild>
              <Link to="/chat">{content.cta.chatButton}</Link>
            </Button>
            <Button asChild variant="outline">
              <Link to="/practices">{content.cta.practicesButton}</Link>
            </Button>
          </div>
        </section>
      </article>
    </PublicShell>
  );
};

export default SpiritualGuideForAnxietyPage;
