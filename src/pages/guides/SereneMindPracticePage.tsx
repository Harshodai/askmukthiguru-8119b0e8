import { PublicShell } from '@/components/layout/PublicShell';
import { usePageMeta } from '@/hooks/usePageMeta';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { buildCanonical } from '@/lib/domain';
import { useTranslation } from 'react-i18next';
import { getSereneMindPracticeContent } from '@/lib/guidesContent';
import { buildGuideStructuredData } from '@/lib/guideStructuredData';
import { LaunchUpdatesSignup } from '@/components/guides/LaunchUpdatesSignup';

const SereneMindPracticePage = () => {
  const { t, i18n } = useTranslation();
  const content = getSereneMindPracticeContent(t);
  const canonicalUrl = buildCanonical('/guides/serene-mind-practice');

  usePageMeta({
    title: content.meta.title,
    description: content.meta.description,
    canonical: canonicalUrl,
    ogType: 'article',
    jsonLd: buildGuideStructuredData({
      canonicalUrl,
      headline: content.meta.articleHeadline,
      description: content.meta.articleDescription,
      language: i18n.language,
      faqs: content.faqs.items,
      keywords: '3 minute meditation, Serene Mind practice, comfortable breathing, spiritual self-help, daily reflection',
    }),
  });

  return (
    <PublicShell title={content.meta.publicShellTitle}>
      <article className="mx-auto max-w-3xl px-4 pt-28 pb-10 space-y-8 text-foreground/90 leading-relaxed">
        <header className="space-y-3">
          <h1 className="text-3xl sm:text-4xl font-serif font-semibold text-foreground">
            {content.header.title}
          </h1>
          <p className="text-muted-foreground">
            {content.header.subtitle}
          </p>
          <div className="flex flex-wrap gap-2 pt-2">
            <Button asChild><Link to="/practices/serene-mind">{t('guides.aiSpiritualCompanion.cta.practiceButton')}</Link></Button>
            <Button asChild variant="outline"><Link to="/trust">{t('trust.title')}</Link></Button>
          </div>
        </header>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">{content.whatIs.heading}</h2>
          <p>{content.whatIs.body}</p>
          <h3 className="text-lg font-semibold text-foreground pt-2">{content.whatIs.whyRateHeading}</h3>
          <p>{content.whatIs.whyRateBody}</p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">{content.steps.heading}</h2>
          {content.steps.items.map((step, idx) => (
            <div key={idx} className={idx > 0 ? 'space-y-1 pt-2' : 'space-y-1'}>
              <h3 className="text-lg font-semibold text-foreground">{step.title}</h3>
              <p>{step.body}</p>
            </div>
          ))}
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold text-foreground">{content.whenToUse.heading}</h2>
          <ul className="list-disc pl-6 space-y-1">
            {content.whenToUse.items.map((item, idx) => (
              <li key={idx}>{item}</li>
            ))}
          </ul>
          <p>{content.whenToUse.note}</p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">{content.mistakes.heading}</h2>
          {content.mistakes.items.map((m, idx) => (
            <div key={idx} className={idx > 0 ? 'space-y-1 pt-2' : 'space-y-1'}>
              <h3 className="text-lg font-semibold text-foreground">{m.title}</h3>
              <p>{m.body}</p>
            </div>
          ))}
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold text-foreground">{content.doorway.heading}</h2>
          <p>
            {content.doorway.part1}
            <Link to="/guides/beautiful-state-meditation" className="text-ojas-ink dark:text-ojas underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm">
              {content.doorway.beautifulStateLink}
            </Link>
            {content.doorway.part2}
            <Link to="/practices" className="text-ojas-ink dark:text-ojas underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm">
              {content.doorway.findPracticesLink}
            </Link>
            {content.doorway.part3}
            <Link to="/guides/ai-spiritual-companion" className="text-ojas-ink dark:text-ojas underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm">
              {content.doorway.aiCompanionLink}
            </Link>
            {content.doorway.part4}
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

        <section className="space-y-3 border-t border-border pt-6">
          <h2 className="text-xl font-semibold text-foreground">{content.cta.heading}</h2>
          <p>{content.cta.body}</p>
          <a href="https://www.theonenessmovement.org/products" target="_blank" rel="noopener noreferrer" className="inline-block text-ojas-ink dark:text-ojas underline focus-visible:ring-2 focus-visible:ring-ring">
            {t('trust.sourcesTitle')} · Oneness Movement
          </a>
          <div className="flex flex-wrap gap-2 pt-2">
            <Button asChild>
              <Link to="/chat">{content.cta.chatButton}</Link>
            </Button>
            <Button asChild variant="outline">
              <Link to="/practices">{content.cta.exploreButton}</Link>
            </Button>
          </div>
          <LaunchUpdatesSignup source="guide_serene_mind" />
        </section>
      </article>
    </PublicShell>
  );
};

export default SereneMindPracticePage;
