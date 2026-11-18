import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { Menu, X, ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useState } from 'react';
import { UserMenu } from '@/components/common/UserMenu';
import { WhatsAppButton } from '@/components/common/WhatsAppButton';
import { EkamLotusIcon } from '@/components/common/EkamLinkButton';

export const Navbar = () => {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);

  const navLinks = [
    { href: '#gurus', label: t('nav.meetGurus') },
    { href: '#how-it-works', label: t('nav.howItWorks') },
    { href: '#practices', label: t('nav.practices') },
    { href: '#wisdom', label: t('nav.wisdom', 'Wisdom') },
    { href: '/knowledge-graph', label: t('nav.wisdomMap', 'Wisdom Map'), isRoute: true },
    {
      href: 'https://www.ekam.org',
      label: 'Ekam',
      isExternal: true,
      testId: 'navbar-ekam-button',
    },
  ];

  return (
    <motion.nav
      initial={{ y: -100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="fixed top-0 left-0 right-0 z-50 flex justify-center"
    >
      <div className="w-full max-w-5xl mx-4 mt-5">
        <div className="rounded-full bg-background/70 backdrop-blur-2xl ring-1 ring-border/40 px-4 sm:px-6 py-2.5 sm:py-3 shadow-[0_8px_32px_0_rgba(0,0,0,0.10)]">
          <div className="flex items-center justify-between gap-2">

            {/* Logo */}
            <Link to="/" className="flex items-center gap-2 shrink-0">
              <span className="text-lg" aria-hidden="true">🙏</span>
              <span className="text-lg font-bold text-gradient-gold">{t('nav.appName')}</span>
            </Link>

            {/* Desktop Navigation Links */}
            <div className="hidden md:flex items-center gap-6 lg:gap-7">
              {navLinks.map((link) => (
                link.isRoute ? (
                  <Link
                    key={link.href}
                    to={link.href}
                    className="text-sm text-foreground/85 hover:text-ojas transition-colors duration-200 font-medium"
                  >
                    {link.label}
                  </Link>
                ) : link.isExternal ? (
                  <a
                    key={link.href}
                    href={link.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-foreground/85 hover:text-ojas transition-colors duration-200 font-medium inline-flex items-center gap-1"
                    data-testid={link.testId}
                  >
                    <span>{link.label}</span>
                    <ExternalLink className="w-3 h-3 opacity-60" aria-hidden="true" />
                  </a>
                ) : (
                  <a
                    key={link.href}
                    href={link.href}
                    className="text-sm text-foreground/85 hover:text-ojas transition-colors duration-200 font-medium"
                  >
                    {link.label}
                  </a>
                )
              ))}
            </div>

            {/* Action Group */}
            <div className="flex items-center gap-2 sm:gap-2.5">
              <Link
                to="/chat"
                className="hidden md:inline-flex px-5 py-2 bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-medium rounded-full text-sm transition-all duration-300 hover:scale-105 shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ojas focus-visible:ring-offset-2"
              >
                {t('nav.startChat')}
              </Link>

              {/* WhatsApp Community Action */}
              <div className="hidden md:flex items-center">
                <WhatsAppButton data-testid="navbar-whatsapp-button" />
              </div>

              {/* User Menu (Desktop) */}
              <div className="hidden md:flex items-center">
                <UserMenu />
              </div>

              {/* Mobile Menu Button (Single clean touch control on mobile) */}
              <button
                onClick={() => setIsOpen(!isOpen)}
                className="md:hidden p-2 text-foreground hover:text-ojas transition-colors rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ojas focus-visible:ring-offset-2 min-h-[44px] min-w-[44px] flex items-center justify-center"
                aria-label={isOpen ? t('common.closeNav') : t('common.openNav')}
                aria-expanded={isOpen}
                aria-controls="mobile-nav"
              >
                {isOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
              </button>
            </div>
          </div>

          {/* Mobile Navigation Drawer */}
          {isOpen && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="md:hidden mt-3 pt-3 border-t border-border/40"
            >
              <div className="flex flex-col gap-3">
                {navLinks.map((link) => (
                  link.isRoute ? (
                    <Link
                      key={link.href}
                      to={link.href}
                      onClick={() => setIsOpen(false)}
                      className="text-foreground hover:text-ojas transition-colors font-medium text-sm py-1"
                    >
                      {link.label}
                    </Link>
                  ) : link.isExternal ? (
                    <a
                      key={link.href}
                      href={link.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={() => setIsOpen(false)}
                      className="text-foreground hover:text-ojas transition-colors font-medium text-sm py-1 flex items-center justify-between"
                    >
                      <span className="flex items-center gap-2">
                        <EkamLotusIcon className="w-4 h-4 text-ojas" />
                        <span>Ekam · World Centre</span>
                      </span>
                      <ExternalLink className="w-3.5 h-3.5 opacity-60" />
                    </a>
                  ) : (
                    <a
                      key={link.href}
                      href={link.href}
                      onClick={() => setIsOpen(false)}
                      className="text-foreground hover:text-ojas transition-colors font-medium text-sm py-1"
                    >
                      {link.label}
                    </a>
                  )
                ))}

                <div className="pt-2 border-t border-border/30 flex flex-col gap-2">
                  <WhatsAppButton variant="pill" className="w-full justify-center" onClick={() => setIsOpen(false)} />
                  <Link
                    to="/chat"
                    onClick={() => setIsOpen(false)}
                    className="w-full px-5 py-2.5 bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-medium rounded-full text-center shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ojas"
                  >
                    {t('nav.startChat')}
                  </Link>
                </div>
              </div>
            </motion.div>
          )}
        </div>
      </div>
    </motion.nav>
  );
};
