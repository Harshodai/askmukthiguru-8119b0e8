import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Sparkles } from 'lucide-react';
import { usePageMeta } from '@/hooks/usePageMeta';

const PrivacyPage = () => {
  const { t, i18n } = useTranslation();
  usePageMeta({
    title: t('privacy.pageTitle'),
    description: t('privacy.pageDescription'),
    canonical: 'https://askmukthiguru.lovable.app/privacy',
  });
  // Fixed revision date (checked in at build/release time)
  const PRIVACY_REVISION_DATE = '2026-07-11';
  return (
  <main className="min-h-dvh bg-background text-foreground px-4 py-10">
    <div className="max-w-2xl mx-auto space-y-6">
      <Link to="/" className="inline-flex items-center gap-2 text-ojas hover:underline">
        <Sparkles className="w-4 h-4" /> AskMukthiGuru
      </Link>
      <h1 className="text-2xl font-semibold">{t('privacy.title')}</h1>
      <p className="text-sm text-muted-foreground">{t('privacy.lastUpdated', { date: new Date(PRIVACY_REVISION_DATE).toLocaleDateString(i18n.language) })}</p>
      <section className="prose prose-sm dark:prose-invert max-w-none">
        <p>{t('privacy.intro')}</p>
        <h2>{t('privacy.whatWeStore')}</h2>
        <ul>
          <li>{t('privacy.storeEmail')}</li>
          <li>{t('privacy.storeChats')}</li>
          <li>{t('privacy.storeMeditation')}</li>
        </ul>
        <h2>{t('privacy.whatWeNeverDo')}</h2>
        <ul>
          <li>{t('privacy.neverSell')}</li>
          <li>{t('privacy.neverTrain')}</li>
          <li>{t('privacy.neverAds')}</li>
        </ul>
        <h2>{t('privacy.yourRights')}</h2>
        <p>
          {t('privacy.exportDeletion')}
          <a href="mailto:privacy@askmukthiguru.com"> privacy@askmukthiguru.com</a>.
        </p>
        <h2>{t('privacy.aiDisclosure')}</h2>
        <p>{t('privacy.aiDisclosureText')}</p>
      </section>
      <Link to="/" className="text-sm text-ojas hover:underline">{t('privacy.backToHome')}</Link>
    </div>
  </main>
  );
};

export default PrivacyPage;
