import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Sparkles } from 'lucide-react';
import { usePageMeta } from '@/hooks/usePageMeta';
import { buildCanonical } from '@/lib/domain';
import { PublicShell } from '@/components/layout/PublicShell';

const TermsPage = () => {
  const { t, i18n } = useTranslation();
  usePageMeta({
    title: t('terms.pageTitle'),
    description: t('terms.pageDescription'),
    canonical: buildCanonical('/terms'),
  });

  const TERMS_REVISION_DATE = '2026-07-11';

  return (
    <PublicShell>
      <article className="w-full">
        <header className="max-w-3xl mx-auto px-4 sm:px-6 pt-10 sm:pt-14 pb-6 sm:pb-8">
          <div className="flex items-center gap-2 text-sm text-ojas mb-5">
            <Sparkles className="w-4 h-4" aria-hidden="true" />
            <span>AskMukthiGuru</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-foreground">{t('terms.title')}</h1>
          <p className="text-sm text-muted-foreground mt-2">
            {t('terms.lastUpdated', {
              date: new Date(TERMS_REVISION_DATE).toLocaleDateString(i18n.language),
            })}
          </p>
        </header>
        <section className="max-w-3xl mx-auto px-4 sm:px-6 pb-14">
          <div className="rounded-3xl border border-hairline bg-card/80 backdrop-blur-md px-5 py-7 sm:px-8 sm:py-9 shadow-sm">
            <div className="prose prose-sm sm:prose-base dark:prose-invert max-w-none">
              <h2>{t('terms.useOfService')}</h2>
              <p>{t('terms.useOfServiceText')}</p>
              <h2>{t('terms.notMedical')}</h2>
              <p>{t('terms.notMedicalText')}</p>
              <h2>{t('terms.intellectualProperty')}</h2>
              <p>{t('terms.intellectualPropertyText')}</p>
              <h2>{t('terms.accountTermination')}</h2>
              <p>{t('terms.accountTerminationText')}</p>
              <h2>{t('terms.changes')}</h2>
              <p>{t('terms.changesText')}</p>
            </div>
          </div>
          <Link to="/" className="inline-flex mt-6 text-sm text-ojas hover:underline">
            {t('terms.backToHome')}
          </Link>
        </section>
      </article>
    </PublicShell>
  );
};

export default TermsPage;
