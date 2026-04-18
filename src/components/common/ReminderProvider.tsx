import { useMeditationReminder } from '@/hooks/useMeditationReminder';

/**
 * Mounted once at the app root so meditation reminders fire while the tab
 * is open, regardless of which route the user is on.
 */
export const ReminderProvider = ({ children }: { children: React.ReactNode }) => {
  useMeditationReminder();
  return <>{children}</>;
};
