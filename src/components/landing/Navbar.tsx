import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { Menu, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useState } from 'react';
import { UserMenu } from '@/components/common/UserMenu';
import { GetHelpNow } from '@/components/common/GetHelpNow';

const WhatsAppIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg
    viewBox="0 0 24 24"
    fill="currentColor"
    className={className}
    aria-hidden="true"
  >
    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L0 24l6.335-1.662c1.746.953 3.71 1.455 5.711 1.456h.005c6.554 0 11.89-5.336 11.893-11.893a11.821 11.821 0 00-3.48-8.414z" />
  </svg>
);

export const Navbar = () => {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const rawWhatsApp = (import.meta.env.VITE_WHATSAPP_NUMBER || '').trim();
  const whatsappNumber = rawWhatsApp.replace(/[^0-9]/g, '');
  const whatsappUrl = whatsappNumber
    ? `https://wa.me/${whatsappNumber}?text=Namaste%20Mukthi%20Guru`
    : 'https://wa.me/?text=Namaste%20Mukthi%20Guru';

  const navLinks = [
    { href: '#gurus', label: t('nav.meetGurus') },
    { href: '#how-it-works', label: t('nav.howItWorks') },
    { href: '#practices', label: t('nav.practices') },
    { href: '#wisdom', label: t('nav.wisdom', 'Wisdom') },
    { href: '/knowledge-graph', label: t('nav.wisdomMap', 'Wisdom Map'), isRoute: true },
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
            <div className="hidden md:flex items-center gap-6 lg:gap-8">
              {navLinks.map((link) => (
                link.isRoute ? (
                  <Link
                    key={link.href}
                    to={link.href}
                    className="text-sm text-foreground hover:text-ojas transition-colors duration-200 font-medium"
                  >
                    {link.label}
                  </Link>
                ) : (
                  <a
                    key={link.href}
                    href={link.href}
                    className="text-sm text-foreground hover:text-ojas transition-colors duration-200 font-medium"
                  >
                    {link.label}
                  </a>
                )
              ))}
              <Link
                to="/chat"
                className="px-5 py-2 bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-medium rounded-full text-sm transition-all duration-300 hover:scale-105 shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ojas focus-visible:ring-offset-2"
              >
                {t('nav.startChat')}
              </Link>
              <a
                href={whatsappUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="min-h-[44px] min-w-[44px] h-9 w-9 text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 dark:hover:text-emerald-300 transition-colors flex items-center justify-center rounded-xl hover:bg-emerald-500/10"
                aria-label={t('chat.chatOnWhatsApp', 'Chat on WhatsApp')}
                title={t('chat.chatOnWhatsApp', 'Chat on WhatsApp')}
                data-testid="navbar-whatsapp-button"
              >
                <WhatsAppIcon className="w-5 h-5 fill-current" />
              </a>
              <UserMenu />
            </div>

            {/* Mobile WhatsApp Action */}
            <a
              href={whatsappUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="md:hidden min-h-[44px] min-w-[44px] h-9 w-9 text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 dark:hover:text-emerald-300 transition-colors flex items-center justify-center rounded-xl hover:bg-emerald-500/10 ml-auto mr-1"
              aria-label={t('chat.chatOnWhatsApp', 'Chat on WhatsApp')}
              title={t('chat.chatOnWhatsApp', 'Chat on WhatsApp')}
              data-testid="navbar-mobile-whatsapp-button"
            >
              <WhatsAppIcon className="w-5 h-5 fill-current" />
            </a>

            {/* Always visible, including on phones (WCAG 3.2.6) */}
            <GetHelpNow className="mr-2 md:mr-0" />

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
                  link.isRoute ? (
                    <Link
                      key={link.href}
                      to={link.href}
                      onClick={() => setIsOpen(false)}
                      className="text-foreground hover:text-ojas transition-colors font-medium"
                    >
                      {link.label}
                    </Link>
                  ) : (
                    <a
                      key={link.href}
                      href={link.href}
                      onClick={() => setIsOpen(false)}
                      className="text-foreground hover:text-ojas transition-colors font-medium"
                    >
                      {link.label}
                    </a>
                  )
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
