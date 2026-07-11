import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Sparkles } from 'lucide-react';
import { usePageMeta } from '@/hooks/usePageMeta';

const TermsPage = () => {
  const { t, i18n } = useTranslation();
  usePageMeta({
    title: t('terms.pageTitle'),
    description: t('terms.pageDescription'),
    canonical: 'https://askmukthiguru.lovable.app/terms',
  });
  // Fixed revision date (checked in at build/release time)
  const TERMS_REVISION_DATE = '2026-07-11';
  return (
  <main className="min-h-dvh bg-background text-foreground px-4 py-10">
    <div className="max-w-2xl mx-auto space-y-6">
      <Link to="/" className="inline-flex items-center gap-2 text-ojas hover:underline">
        <Sparkles className="w-4 h-4" /> AskMukthiGuru
      </Link>
      <h1 className="text-2xl font-semibold">{t('terms.title')}</h1>
      <p className="text-sm text-muted-foreground">{t('terms.lastUpdated', { date: new Date(TERMS_REVISION_DATE).toLocaleDateString(i18n.language) })}</p>
      <section className="prose prose-sm dark:prose-invert max-w-none">
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
      </section>
      <Link to="/" className="text-sm text-ojas hover:underline">{t('terms.backToHome')}</Link>
    </div>
  </main>
  );
};

export default TermsPage;
