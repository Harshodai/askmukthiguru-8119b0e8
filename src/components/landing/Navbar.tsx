import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Menu,
  X,
  ExternalLink,
  ChevronRight,
  Sparkles,
  HelpCircle,
  Compass,
  BookOpen,
  Network,
  ArrowRight,
  User,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { UserMenu } from '@/components/common/UserMenu';
import { WhatsAppButton } from '@/components/common/WhatsAppButton';
import { EkamLotusIcon } from '@/components/common/EkamLinkButton';
import { useProfile } from '@/hooks/useProfile';
import { getInitials } from '@/lib/profileStorage';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';

export const Navbar = () => {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const { profile } = useProfile();

  const navLinks = [
    { href: '#gurus', label: t('nav.meetGurus'), icon: Sparkles },
    { href: '#how-it-works', label: t('nav.howItWorks'), icon: HelpCircle },
    { href: '#practices', label: t('nav.practices'), icon: Compass },
    { href: '#wisdom', label: t('nav.wisdom', 'Wisdom'), icon: BookOpen },
    { href: '/knowledge-graph', label: t('nav.wisdomMap', 'Wisdom Map'), isRoute: true, icon: Network },
    {
      href: 'https://www.ekam.org',
      label: 'Ekam',
      isExternal: true,
      testId: 'navbar-ekam-button',
      icon: EkamLotusIcon,
    },
  ];

  // Prevent background scroll when mobile drawer is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  // Handle ESC key to close mobile drawer
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsOpen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  return (
    <>
      {/* ── Fixed Floating Capsule Navbar (Desktop & Mobile Closed State) ── */}
      <motion.nav
        initial={{ y: -100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.5 }}
        className="fixed top-0 left-0 right-0 z-40 flex justify-center pointer-events-none"
      >
        <div className="w-full max-w-5xl mx-4 mt-5 pointer-events-auto">
          <div className="rounded-full bg-background/80 backdrop-blur-2xl ring-1 ring-border/40 px-4 sm:px-6 py-2.5 sm:py-3 shadow-[0_8px_32px_0_rgba(0,0,0,0.10)]">
            <div className="flex items-center justify-between gap-2">
              {/* Logo */}
              <Link to="/" className="flex items-center gap-2 shrink-0">
                <span className="text-lg" aria-hidden="true">🙏</span>
                <span className="text-lg font-bold text-gradient-gold">{t('nav.appName')}</span>
              </Link>

              {/* Desktop Navigation Links */}
              <div className="hidden md:flex items-center gap-6 lg:gap-7">
                {navLinks.map((link) =>
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
                  ),
                )}
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
                  onClick={() => setIsOpen(true)}
                  className="md:hidden p-2 text-foreground hover:text-ojas transition-colors rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ojas focus-visible:ring-offset-2 min-h-[44px] min-w-[44px] flex items-center justify-center"
                  aria-label={t('common.openNav')}
                  aria-expanded={isOpen}
                  aria-controls="mobile-nav"
                >
                  <Menu className="w-6 h-6" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </motion.nav>

      {/* ── Mobile Sanctuary Navigation Drawer & Backdrop (Apple HIG Standard) ── */}
      <AnimatePresence>
        {isOpen && (
          <div className="md:hidden">
            {/* Backdrop Scrim */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
              onClick={() => setIsOpen(false)}
              className="fixed inset-0 z-[65] bg-black/60 backdrop-blur-md"
              aria-hidden="true"
            />

            {/* Full-Screen Luxury Sanctuary Drawer */}
            <motion.div
              id="mobile-nav"
              role="dialog"
              aria-modal="true"
              aria-label={t('common.navigation', 'Navigation')}
              initial={{ y: '-100%', opacity: 0.6 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: '-100%', opacity: 0 }}
              transition={{ duration: 0.35, ease: [0.32, 0.72, 0, 1] }}
              className="fixed inset-0 z-[70] bg-background/98 dark:bg-background/98 backdrop-blur-3xl flex flex-col overflow-hidden safe-top safe-bottom"
            >
              {/* Header inside Drawer */}
              <div className="px-5 pt-4 pb-3.5 border-b border-border/40 flex items-center justify-between shrink-0">
                <Link
                  to="/"
                  onClick={() => setIsOpen(false)}
                  className="flex items-center gap-2"
                >
                  <span className="text-xl" aria-hidden="true">🙏</span>
                  <span className="text-lg font-bold text-gradient-gold">{t('nav.appName')}</span>
                </Link>
                <button
                  onClick={() => setIsOpen(false)}
                  className="w-10 h-10 rounded-full bg-card/80 border border-border/50 flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-card transition-all active:scale-95"
                  aria-label={t('common.closeNav')}
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Scrollable Drawer Content */}
              <div className="flex-1 p-5 space-y-4 overflow-y-auto">
                {/* Seeker Profile Card */}
                <div className="p-3.5 rounded-2xl bg-card/60 border border-border/40 flex items-center justify-between shadow-xs">
                  <div className="flex items-center gap-3 min-w-0">
                    <Avatar className="w-10 h-10 ring-1 ring-ojas/20 shrink-0">
                      {profile.avatarDataUrl || profile.avatarUrl ? (
                        <AvatarImage src={profile.avatarDataUrl ?? profile.avatarUrl ?? ''} />
                      ) : null}
                      <AvatarFallback className="bg-ojas/10 text-ojas text-sm font-semibold">
                        {getInitials(profile.displayName) || <User className="w-5 h-5 text-muted-foreground" />}
                      </AvatarFallback>
                    </Avatar>
                    <div className="min-w-0">
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
                        {t('profile.seeker', 'Seeker')}
                      </p>
                      <p className="text-sm font-medium text-foreground truncate">
                        {profile.displayName || t('profile.devotedSeeker', 'Devoted Seeker')}
                      </p>
                    </div>
                  </div>
                  <Link
                    to="/profile"
                    onClick={() => setIsOpen(false)}
                    className="px-3 py-1.5 rounded-full text-xs font-medium bg-ojas/10 text-ojas hover:bg-ojas/20 transition-colors inline-flex items-center gap-1 shrink-0"
                  >
                    <span>{t('nav.profile', 'Profile')}</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </Link>
                </div>

                {/* Structured Navigation Rows */}
                <div className="rounded-2xl border border-border/40 bg-card/40 divide-y divide-border/30 overflow-hidden shadow-xs">
                  {navLinks
                    .filter((l) => !l.isExternal)
                    .map((link) => {
                      const Icon = link.icon;
                      const content = (
                        <div className="flex items-center justify-between px-4 py-3.5 hover:bg-ojas/5 transition-colors active:scale-[0.99]">
                          <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-lg bg-ojas/10 flex items-center justify-center text-ojas shrink-0">
                              <Icon className="w-4 h-4" />
                            </div>
                            <span className="text-sm font-medium text-foreground">{link.label}</span>
                          </div>
                          <ChevronRight className="w-4 h-4 text-muted-foreground/40" />
                        </div>
                      );

                      return link.isRoute ? (
                        <Link
                          key={link.href}
                          to={link.href}
                          onClick={() => setIsOpen(false)}
                          className="block"
                        >
                          {content}
                        </Link>
                      ) : (
                        <a
                          key={link.href}
                          href={link.href}
                          onClick={() => setIsOpen(false)}
                          className="block"
                        >
                          {content}
                        </a>
                      );
                    })}
                </div>

                {/* Featured Sanctuary Card: Ekam */}
                <a
                  href="https://www.ekam.org"
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() => setIsOpen(false)}
                  className="block p-4 rounded-2xl bg-gradient-to-r from-ojas/10 via-card/70 to-ojas/5 border border-ojas/30 hover:border-ojas/50 transition-all shadow-xs"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-10 h-10 rounded-xl bg-ojas/15 border border-ojas/30 flex items-center justify-center shrink-0">
                        <EkamLotusIcon className="w-5 h-5 text-ojas" />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="text-sm font-semibold text-foreground truncate">
                            Ekam · World Centre
                          </span>
                          <ExternalLink className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                          {t('nav.ekamSubtitle', 'World Centre for Enlightenment · India')}
                        </p>
                      </div>
                    </div>
                    <ChevronRight className="w-4 h-4 text-muted-foreground/50 shrink-0" />
                  </div>
                </a>

                {/* Action Footer: WhatsApp & Start Chat */}
                <div className="pt-2 pb-6 space-y-2.5">
                  <WhatsAppButton
                    variant="pill"
                    className="w-full justify-center h-11"
                    data-testid="navbar-mobile-whatsapp-button"
                    onClick={() => setIsOpen(false)}
                  />
                  <Link
                    to="/chat"
                    onClick={() => setIsOpen(false)}
                    className="w-full h-12 flex items-center justify-center gap-2 bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-semibold rounded-full text-center shadow-md active:scale-[0.98] transition-transform"
                  >
                    <span>{t('nav.startChat')}</span>
                    <ArrowRight className="w-4 h-4" />
                  </Link>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
};
