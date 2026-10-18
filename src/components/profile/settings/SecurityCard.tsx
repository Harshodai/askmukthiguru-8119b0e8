import { useTranslation } from 'react-i18next';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { TwoFactorSettings } from '@/components/auth/TwoFactorSettings';
import { useNavigate } from 'react-router-dom';

interface SecurityCardProps {
  setupMfaRedirect: string | null;
}

export const SecurityCard = ({ setupMfaRedirect }: SecurityCardProps) => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <>
      {setupMfaRedirect && (
        <Alert className="rounded-2xl border border-hairline">
          <AlertDescription>
            {t('profile.danger.mfaRequired', 'Admin access requires two-factor authentication. Set it up below, then you will be sent back automatically.')}
          </AlertDescription>
        </Alert>
      )}
      <div id="security" className="scroll-mt-20">
        <TwoFactorSettings
          onEnrolled={setupMfaRedirect ? () => navigate(setupMfaRedirect, { replace: true }) : undefined}
        />
      </div>
    </>
  );
};
