import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { usePageMeta } from '@/hooks/usePageMeta';
import { Sparkles, Search, Home } from 'lucide-react';
import { getSupportEmail } from '@/lib/domain';

const NotFound = () => {
  const { t } = useTranslation();
  
  usePageMeta({
    title: t('notFound.pageTitle', 'Page Not Found — AskMukthiGuru'),
    description: t('notFound.pageDescription', 'The page you\'re looking for doesn\'t exist.'),
    noindex: true,
  });

  return (
    <div className="min-h-dvh flex items-center justify-center bg-gradient-to-br from-background via-background to-ojas/5 px-4 relative overflow-hidden">
      {/* Ambient radial glow */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 60% 40% at 50% 0%, hsl(var(--ojas-gold) / 0.10), transparent 70%)',
        }}
      />
      
      <main className="relative w-full max-w-md mx-auto text-center space-y-8 py-16">
        <Link to="/" className="inline-flex items-center gap-2 text-ojas hover:underline">
          <Sparkles className="w-5 h-5" />
          AskMukthiGuru
        </Link>
        
        <div className="space-y-4">
          <h1 className="text-6xl font-bold text-foreground tracking-tight">404</h1>
          <p className="text-xl text-muted-foreground">
            {t('notFound.message', 'Oops! The page you\'re looking for doesn\'t exist.')}
          </p>
          <p className="text-sm text-muted-foreground/80">
            {t('notFound.suggestion', 'It might have been moved or the URL was typed incorrectly.')}
          </p>
        </div>
        
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <Link
            to="/"
            className="inline-flex items-center gap-2 px-6 py-3 bg-ojas text-primary-foreground rounded-xl font-medium hover:bg-ojas-light transition-colors"
          >
            <Home className="w-4 h-4" />
            {t('notFound.returnHome', 'Return Home')}
          </Link>
          <Link
            to="/chat"
            className="inline-flex items-center gap-2 px-6 py-3 border border-border rounded-xl font-medium hover:bg-accent transition-colors"
          >
            <Search className="w-4 h-4" />
            {t('notFound.startChat', 'Start Chatting')}
          </Link>
        </div>
        
        <p className="text-xs text-muted-foreground/60 pt-4 border-t border-border/50">
          {t('notFound.helpText', 'Need help? Check our')}{' '}
          <Link to="/guides" className="text-ojas hover:underline">
            {t('notFound.guides', 'guides')}
          </Link>
          {' '}{t('notFound.orContact', 'or contact')}{' '}
          <a href={`mailto:${getSupportEmail()}`} className="text-ojas hover:underline">
            {getSupportEmail()}
          </a>
        </p>
      </main>
    </div>
  );
};

export default NotFound;