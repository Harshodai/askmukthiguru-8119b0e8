import { useTranslation } from 'react-i18next';
import { forwardRef } from 'react';
import { motion } from 'framer-motion';
import { Heart, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';

export const Footer = forwardRef<HTMLElement>((_, ref) => {
  const { t } = useTranslation();
  return (
    <footer ref={ref} className="py-12 pb-[calc(3rem+env(safe-area-inset-bottom))] relative overflow-hidden border-t border-border bg-muted/30">
      <div className="relative z-10 container mx-auto px-6">
        <div className="flex flex-col items-center text-center">
          {/* Logo */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="flex items-center gap-2 mb-4"
          >
            <Sparkles className="w-6 h-6 text-ojas" />
            <span className="text-h3 text-gradient-gold">{t('nav.appName')}</span>
          </motion.div>

          {/* Tagline */}
          <p className="text-body-sm mb-6 max-w-md">
            {t('landing.footer.tagline')}
          </p>

          {/* Links */}
          <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 mb-8">
            <Link to="/" className="text-caption hover:text-ojas transition-colors">
              {t('nav.home')}
            </Link>
            <Link to="/chat" className="text-caption hover:text-ojas transition-colors">
              {t('nav.chat')}
            </Link>
            <Link to="/practices" className="text-caption hover:text-ojas transition-colors">
              Practices
            </Link>
            <Link to="/guides/ai-spiritual-companion" className="text-caption hover:text-ojas transition-colors">
              AI Meditation Guide
            </Link>
            <Link to="/guides/spirit-guides" className="text-caption hover:text-ojas transition-colors">
              Spirit Guides
            </Link>
            <a href="#gurus" className="text-caption hover:text-ojas transition-colors">
              {t('nav.about')}
            </a>
          </div>

          {/* Disclaimer */}
          <div className="text-caption max-w-lg mb-6 bg-muted/50 rounded-lg p-3">
            <p>{t('landing.footer.disclaimer')}</p>
          </div>

          {/* Copyright */}
          <div className="flex items-center gap-1 text-caption">
            <span>{t('landing.footer.madeWith')}</span>
            <Heart className="w-4 h-4 text-ojas fill-ojas" />
            <span>{t('landing.footer.forSeekers')}</span>
          </div>

        </div>
      </div>
    </footer>
  );
});

Footer.displayName = 'Footer';
