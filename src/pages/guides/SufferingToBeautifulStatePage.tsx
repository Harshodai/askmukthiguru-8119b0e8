import { PublicShell } from '@/components/layout/PublicShell';
import { usePageMeta } from '@/hooks/usePageMeta';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { buildCanonical } from '@/lib/domain';
import { useTranslation } from 'react-i18next';
import { getSufferingToBeautifulStateContent } from '@/lib/guidesContent';

const SufferingToBeautifulStatePage = () => {
  const { t } = useTranslation();
  const content = getSufferingToBeautifulStateContent(t);
  const canonicalUrl = buildCanonical('/guides/suffering-to-beautiful-state');

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
          keywords: 'suffering state, beautiful state, suffering state vs beautiful state, Preethaji Krishnaji',
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
          <h2 className="text-xl font-semibold text-foreground">{content.difference.heading}</h2>
          <p>{content.difference.body}</p>
          <h3 className="text-lg font-semibold text-foreground pt-2">{content.difference.sameSituationHeading}</h3>
          <p>{content.difference.sameSituationBody}</p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">{content.whyDefault.heading}</h2>
          <p>
            {content.whyDefault.part1}
            <Link to="/guides/self-centric-thinking" className="text-ojas underline">
              {content.whyDefault.selfCentricLink}
            </Link>
            {content.whyDefault.part2}
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">{content.steps.heading}</h2>
          <div className="space-y-1">
            <h3 className="text-lg font-semibold text-foreground">{content.steps.step1Title}</h3>
            <p>{content.steps.step1Body}</p>
          </div>
          <div className="space-y-1 pt-2">
            <h3 className="text-lg font-semibold text-foreground">{content.steps.step2Title}</h3>
            <p>{content.steps.step2Body}</p>
          </div>
          <div className="space-y-1 pt-2">
            <h3 className="text-lg font-semibold text-foreground">{content.steps.step3Title}</h3>
            <p>
              {content.steps.step3Part1}
              <Link to="/guides/serene-mind-practice" className="text-ojas underline">
                {content.steps.sereneMindLink}
              </Link>
              {content.steps.step3Part2}
            </p>
          </div>
          <div className="space-y-1 pt-2">
            <h3 className="text-lg font-semibold text-foreground">{content.steps.step4Title}</h3>
            <p>{content.steps.step4Body}</p>
          </div>
          <div className="space-y-1 pt-2">
            <h3 className="text-lg font-semibold text-foreground">{content.steps.step5Title}</h3>
            <p>
              {content.steps.step5Part1}
              <Link to="/guides/beautiful-state-meditation" className="text-ojas underline">
                {content.steps.beautifulStateLink}
              </Link>
              {content.steps.step5Part2}
            </p>
          </div>
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold text-foreground">{content.whyTakesPractice.heading}</h2>
          <p>{content.whyTakesPractice.body}</p>
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold text-foreground">{content.dailyHabit.heading}</h2>
          <p>
            {content.dailyHabit.part1}
            <Link to="/practices" className="text-ojas underline">
              {content.dailyHabit.explorePracticesLink}
            </Link>
            {content.dailyHabit.part2}
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
              <Link to="/guides/beautiful-state-meditation">{content.cta.meditationButton}</Link>
            </Button>
          </div>
        </section>
      </article>
    </PublicShell>
  );
};

export default SufferingToBeautifulStatePage;
