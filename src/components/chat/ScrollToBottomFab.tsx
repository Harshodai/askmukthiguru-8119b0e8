import { useTranslation } from 'react-i18next';
import { ChevronsDown } from 'lucide-react';
import { FloatingActionButton } from '@/components/common/ui/FloatingActionButton';

interface ScrollToBottomFabProps {
  visible: boolean;
  unreadCount: number;
  onClick: () => void;
}

export const ScrollToBottomFab = ({ visible, unreadCount, onClick }: ScrollToBottomFabProps) => {
  const { t } = useTranslation();

  return (
    <FloatingActionButton
      visible={visible}
      onClick={onClick}
      icon={<ChevronsDown className="w-4 h-4 text-ojas" />}
      label={unreadCount > 0 ? t('chat.newMessagesShort', { count: unreadCount }) : t('chat.latest')}
      ariaLabel={unreadCount > 0 ? t('chat.jumpToLatestNew', { count: unreadCount }) : t('chat.jumpToLatest')}
    />
  );
};
