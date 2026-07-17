import { useEffect, useState } from 'react';
import { Toaster as Sonner, toast } from 'sonner';
import { Flame, CheckCircle2, AlertTriangle, Info, XCircle } from 'lucide-react';
import { useTheme } from '@/hooks/useTheme';

type ToasterProps = React.ComponentProps<typeof Sonner>;

/**
 * Warm Sacred toaster.
 *
 * A single toast surface for the app, styled around the Golden Hour palette:
 *   • warm amber/gold accents on a translucent surface
 *   • hairline border in the accent hue at 20% alpha
 *   • layered gold glow shadow for depth
 *   • flame glyph as the identity mark
 *   • serif-ish weight for the title, sans body for the description
 *   • springy enter, soft fade+drift exit (from Sonner defaults)
 *   • mobile-first placement, safe-area aware
 *
 * All colour values pull from the semantic tokens in `index.css` so the
 * theme respects light + dark automatically.
 */
const Toaster = (props: ToasterProps) => {
  const { theme } = useTheme();
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const mql = window.matchMedia('(max-width: 640px)');
    const sync = () => setIsMobile(mql.matches);
    sync();
    mql.addEventListener('change', sync);
    return () => mql.removeEventListener('change', sync);
  }, []);

  return (
    <Sonner
      theme={theme === 'dark' ? 'dark' : theme === 'light' ? 'light' : 'system'}
      position={isMobile ? 'top-center' : 'bottom-right'}
      visibleToasts={3}
      gap={10}
      offset={isMobile ? 16 : 24}
      icons={{
        success: (
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/15 text-primary">
            <CheckCircle2 className="h-3.5 w-3.5" />
          </span>
        ),
        info: (
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-accent/20 text-accent-foreground">
            <Info className="h-3.5 w-3.5" />
          </span>
        ),
        warning: (
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/20 text-primary">
            <AlertTriangle className="h-3.5 w-3.5" />
          </span>
        ),
        error: (
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-destructive/15 text-destructive">
            <XCircle className="h-3.5 w-3.5" />
          </span>
        ),
        loading: <Flame className="h-4 w-4 text-primary animate-pulse" />,
      }}
      toastOptions={{
        unstyled: false,
        classNames: {
          toast: [
            'group relative overflow-hidden',
            'flex items-start gap-3 p-4 pr-10',
            'min-h-[56px] w-full rounded-2xl',
            'border border-primary/20',
            'bg-background/95 backdrop-blur-xl',
            'text-foreground',
            'shadow-[0_8px_32px_-8px_hsl(var(--primary)/0.25),0_2px_8px_hsl(var(--foreground)/0.08)]',
            'font-sans',
          ].join(' '),
          title: 'text-[15px] font-semibold tracking-[-0.01em] leading-tight text-foreground',
          description: 'text-[13px] leading-relaxed text-foreground/70 mt-0.5',
          actionButton:
            'inline-flex items-center rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors',
          cancelButton:
            'inline-flex items-center rounded-lg bg-muted px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted/80 transition-colors',
          closeButton:
            '!absolute !right-2 !top-2 !left-auto !translate-x-0 !translate-y-0 flex h-6 w-6 items-center justify-center rounded-full !bg-transparent hover:!bg-primary/10 !border-0 text-foreground/50 hover:text-foreground/80 transition-colors',
          icon: 'flex-shrink-0 mt-0.5',
          success: '!border-primary/30',
          info: '!border-accent/30',
          warning: '!border-primary/40',
          error: '!border-destructive/30',
        },
        closeButton: true,
        duration: 4500,
      }}
      style={
        {
          // Ambient glow behind the stack
          '--normal-bg': 'hsl(var(--background) / 0.95)',
          '--normal-border': 'hsl(var(--primary) / 0.2)',
          '--normal-text': 'hsl(var(--foreground))',
        } as React.CSSProperties
      }
      {...props}
    />
  );
};

export { Toaster, toast };
