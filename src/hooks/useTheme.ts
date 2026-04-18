import { useEffect, useCallback } from 'react';
import { useProfile } from '@/hooks/useProfile';
import type { ThemePreference } from '@/lib/profileStorage';

const applyTheme = (pref: ThemePreference) => {
  const root = document.documentElement;
  const resolved =
    pref === 'system'
      ? window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'dark'
        : 'light'
      : pref;
  root.classList.toggle('dark', resolved === 'dark');
  root.style.colorScheme = resolved;
};

/**
 * Reactively keeps the html.dark class synced with the user's profile preference.
 * Also listens to OS-level color scheme changes when set to "system".
 */
export const useTheme = () => {
  const { profile, update } = useProfile();
  const theme = profile.theme ?? 'system';

  useEffect(() => {
    applyTheme(theme);

    if (theme !== 'system') return;
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => applyTheme('system');
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, [theme]);

  const setTheme = useCallback(
    (next: ThemePreference) => {
      update({ theme: next });
    },
    [update],
  );

  const toggle = useCallback(() => {
    const isDark = document.documentElement.classList.contains('dark');
    update({ theme: isDark ? 'light' : 'dark' });
  }, [update]);

  return { theme, setTheme, toggle };
};
