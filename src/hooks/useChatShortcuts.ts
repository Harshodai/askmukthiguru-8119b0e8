import { useEffect } from 'react';

interface ShortcutHandlers {
  /** Cmd/Ctrl+Enter — submit the current input */
  onSubmit?: () => void;
  /** Cmd/Ctrl+Shift+O — start a new conversation */
  onNewChat?: () => void;
  /** Cmd/Ctrl+/ — focus the chat input */
  onFocusInput?: () => void;
  /** Whether the shortcuts are active (e.g. only on /chat). */
  enabled?: boolean;
}

/**
 * Registers global keyboard shortcuts for the chat surface.
 * Mirrors ChatGPT / Claude conventions:
 *   - Cmd/Ctrl + Enter         → send message
 *   - Cmd/Ctrl + Shift + O     → new chat
 *   - Cmd/Ctrl + /             → focus input
 * Sidebar toggle (Cmd/Ctrl+B) lives inside `DesktopSidebar` so it works there too.
 */
export const useChatShortcuts = ({
  onSubmit,
  onNewChat,
  onFocusInput,
  enabled = true,
}: ShortcutHandlers) => {
  useEffect(() => {
    if (!enabled) return;
    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod) return;

      // Cmd/Ctrl + Enter → submit
      if (e.key === 'Enter' && onSubmit) {
        e.preventDefault();
        onSubmit();
        return;
      }
      // Cmd/Ctrl + Shift + O → new chat
      if (e.shiftKey && (e.key === 'o' || e.key === 'O') && onNewChat) {
        e.preventDefault();
        onNewChat();
        return;
      }
      // Cmd/Ctrl + / → focus input
      if (e.key === '/' && onFocusInput) {
        e.preventDefault();
        onFocusInput();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [enabled, onSubmit, onNewChat, onFocusInput]);
};
