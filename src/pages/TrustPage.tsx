import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Sparkles } from 'lucide-react';
import { usePageMeta } from '@/hooks/usePageMeta';
import { buildCanonical, getPrivacyEmail } from '@/lib/domain';
import { PublicShell } from '@/components/layout/PublicShell';

/**
 * Public trust page — factual description of current product behaviour only.
 * Every claim here maps to code: grounding states (app/grounding.py),
 * citations (components/chat/CitationCard.tsx), anti-fabrication filtering
 * (services/okf_quality_filter.py), input guardrails (pipeline builder order)
 * and the crisis helpline registry (config/helplines.yaml). No metrics.
 */
const TrustPage = () => {
  const { t, i18n } = useTranslation();
  usePageMeta({
    title: t('trust.pageTitle'),
    description: t('trust.pageDescription'),
    canonical: buildCanonical('/trust'),
  });

  const TRUST_REVISION_DATE = '2026-10-04';

  return (
    <PublicShell>
      <article className="w-full">
        <header className="max-w-3xl mx-auto px-4 sm:px-6 pt-10 sm:pt-14 pb-6 sm:pb-8">
          <div className="flex items-center gap-2 text-sm text-ojas-ink dark:text-ojas mb-5">
            <Sparkles className="w-4 h-4" aria-hidden="true" />
            <span>AskMukthiGuru</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-foreground">
            {t('trust.title')}
          </h1>
          <p className="text-sm text-muted-foreground mt-2">
            {t('trust.lastUpdated', {
              date: new Date(TRUST_REVISION_DATE).toLocaleDateString(i18n.language),
            })}
          </p>
        </header>

        <section className="max-w-3xl mx-auto px-4 sm:px-6 pb-14">
          <div className="rounded-3xl border border-hairline bg-card/80 backdrop-blur-md px-5 py-7 sm:px-8 sm:py-9 shadow-sm">
            <div className="prose prose-sm sm:prose-base dark:prose-invert max-w-none">
              <p>{t('trust.intro')}</p>

              <h2>{t('trust.howTitle')}</h2>
              <p>{t('trust.howBody')}</p>
              <ul>
                <li>{t('trust.grounded')}</li>
                <li>{t('trust.partial')}</li>
                <li>{t('trust.abstained')}</li>
                <li>{t('trust.safetyState')}</li>
                <li>{t('trust.systemError')}</li>
              </ul>

              <h2>{t('trust.neverTitle')}</h2>
              <ul>
                <li>{t('trust.neverFabricate')}</li>
                <li>{t('trust.neverImpersonate')}</li>
                <li>{t('trust.neverInventSources')}</li>
              </ul>

              <h2>{t('trust.safetyTitle')}</h2>
              <p>{t('trust.safetyBody')}</p>

              <h2>{t('trust.sourcesTitle')}</h2>
              <ul>
                <li>{t('trust.teachingsAttribution')}</li>
                <li>{t('trust.transcriptSources')}</li>
                <li>{t('trust.dailySource')}</li>
              </ul>
              <p>
                {t('trust.rightsNote')}{' '}
                <a href={`mailto:${getPrivacyEmail()}`}>{getPrivacyEmail()}</a>.
              </p>

              <h2>{t('trust.privacyTitle')}</h2>
              <p>
                {t('trust.privacyBody')} <Link to="/privacy">{t('privacy.title')}</Link>.
              </p>
            </div>
          </div>
          <Link to="/" className="inline-flex mt-6 text-sm text-ojas-ink dark:text-ojas hover:underline">
            {t('trust.backToHome')}
          </Link>
        </section>
      </article>
    </PublicShell>
  );
};

export default TrustPage;
