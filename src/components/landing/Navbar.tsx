import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { Menu, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useState } from 'react';
import { UserMenu } from '@/components/common/UserMenu';

export const Navbar = () => {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);

  const navLinks = [
    { href: '#gurus', label: t('nav.meetGurus') },
    { href: '#how-it-works', label: t('nav.howItWorks') },
    { href: '#practices', label: t('nav.practices') },
    { href: '#meditation', label: t('nav.meditation') },
  ];

  return (
    <motion.nav
      initial={{ y: -100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="fixed top-0 left-0 right-0 z-50 flex justify-center"
    >
      <div className="w-full max-w-5xl mx-4 mt-5">
        <div className="rounded-full bg-background/60 backdrop-blur-2xl ring-1 ring-border/40 px-6 py-3.5 shadow-[0_8px_32px_0_rgba(0,0,0,0.12)]">
          <div className="flex items-center justify-between">

            {/* Logo */}
            <Link to="/" className="flex items-center gap-2">
              <span className="text-lg" aria-hidden="true">🙏</span>
              <span className="text-lg font-bold text-gradient-gold">{t('nav.appName')}</span>
            </Link>

            {/* Desktop Navigation */}
            <div className="hidden md:flex items-center gap-8">
              {navLinks.map((link) => (
                <a
                  key={link.href}
                  href={link.href}
                  className="text-sm text-foreground hover:text-ojas transition-colors duration-200 font-medium"
                >
                  {link.label}
                </a>
              ))}
              <Link
                to="/chat"
                className="px-5 py-2 bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-medium rounded-full text-sm transition-all duration-300 hover:scale-105 shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ojas focus-visible:ring-offset-2"
              >
                {t('nav.startChat')}
              </Link>
              <UserMenu />
            </div>

            {/* Mobile Menu Button */}
            <button
              onClick={() => setIsOpen(!isOpen)}
              className="md:hidden p-2 text-foreground hover:text-ojas transition-colors rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ojas focus-visible:ring-offset-2"
              aria-label={isOpen ? t('common.closeNav') : t('common.openNav')}
              aria-expanded={isOpen}
              aria-controls="mobile-nav"
            >
              {isOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
          </div>

          {/* Mobile Navigation */}
          {isOpen && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="md:hidden mt-4 pt-4 border-t border-border"
            >
              <div className="flex flex-col gap-4">
                {navLinks.map((link) => (
                  <a
                    key={link.href}
                    href={link.href}
                    onClick={() => setIsOpen(false)}
                    className="text-foreground hover:text-ojas transition-colors font-medium"
                  >
                    {link.label}
                  </a>
                ))}
                <Link
                  to="/chat"
                  onClick={() => setIsOpen(false)}
                  className="px-5 py-2 bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-medium rounded-full text-center transition-all duration-300 shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ojas focus-visible:ring-offset-2"
                >
                  {t('nav.startChat')}
                </Link>
              </div>
            </motion.div>
          )}
        </div>
      </div>
    </motion.nav>
  );
};
