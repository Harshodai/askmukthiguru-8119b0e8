import { useTheme } from '@/hooks/useTheme';

/**
 * Mounted once near the root so theme is applied app-wide,
 * regardless of whether the current route renders an AppShell.
 */
export const ThemeProvider = ({ children }: { children: React.ReactNode }) => {
  useTheme();
  return <>{children}</>;
};
