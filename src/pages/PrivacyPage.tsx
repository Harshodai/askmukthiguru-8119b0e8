import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Sparkles } from 'lucide-react';
import { usePageMeta } from '@/hooks/usePageMeta';
import { buildCanonical, getPrivacyEmail } from '@/lib/domain';
import { PublicShell } from '@/components/layout/PublicShell';

const PrivacyPage = () => {
  const { t, i18n } = useTranslation();
  usePageMeta({
    title: t('privacy.pageTitle'),
    description: t('privacy.pageDescription'),
    canonical: buildCanonical('/privacy'),
  });

  const PRIVACY_REVISION_DATE = '2026-07-11';

  return (
    <PublicShell>
      <article className="w-full">
        <header className="max-w-3xl mx-auto px-4 sm:px-6 pt-10 sm:pt-14 pb-6 sm:pb-8">
          <div className="flex items-center gap-2 text-sm text-ojas mb-5">
            <Sparkles className="w-4 h-4" aria-hidden="true" />
            <span>AskMukthiGuru</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-foreground">{t('privacy.title')}</h1>
          <p className="text-sm text-muted-foreground mt-2">
            {t('privacy.lastUpdated', {
              date: new Date(PRIVACY_REVISION_DATE).toLocaleDateString(i18n.language),
            })}
          </p>
        </header>
        <section className="max-w-3xl mx-auto px-4 sm:px-6 pb-14">
          <div className="rounded-3xl border border-hairline bg-card/80 backdrop-blur-md px-5 py-7 sm:px-8 sm:py-9 shadow-sm">
            <div className="prose prose-sm sm:prose-base dark:prose-invert max-w-none">
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
                <a href={`mailto:${getPrivacyEmail()}`}> {getPrivacyEmail()}</a>.
              </p>
              <h2>{t('privacy.aiDisclosure')}</h2>
              <p>{t('privacy.aiDisclosureText')}</p>
            </div>
          </div>
          <Link to="/" className="inline-flex mt-6 text-sm text-ojas hover:underline">
            {t('privacy.backToHome')}
          </Link>
        </section>
      </article>
    </PublicShell>
  );
};

export default PrivacyPage;
