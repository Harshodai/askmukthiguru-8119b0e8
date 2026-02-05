import { motion } from 'framer-motion';
import { Sparkles, Menu, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useState } from 'react';

export const Navbar = () => {
  const [isOpen, setIsOpen] = useState(false);

  const navLinks = [
    { href: '#gurus', label: 'Meet the Gurus' },
    { href: '#how-it-works', label: 'How It Works' },
    { href: '#meditation', label: 'Meditation' },
  ];

  return (
    <motion.nav
      initial={{ y: -100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="fixed top-0 left-0 right-0 z-50"
    >
      <div className="mx-4 mt-4">
        <div className="glass-card px-6 py-4">
          <div className="flex items-center justify-between">
            {/* Logo */}
            <Link to="/" className="flex items-center gap-2">
              <Sparkles className="w-6 h-6 text-ojas" />
              <span className="text-lg font-bold text-gradient-gold">AskMukthiGuru</span>
            </Link>

            {/* Desktop Navigation */}
            <div className="hidden md:flex items-center gap-8">
              {navLinks.map((link) => (
                <a
                  key={link.href}
                  href={link.href}
                  className="text-sm text-tejas/80 hover:text-ojas transition-colors duration-200"
                >
                  {link.label}
                </a>
              ))}
              <Link
                to="/chat"
                className="px-5 py-2 bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-medium rounded-full text-sm transition-all duration-300 hover:scale-105"
              >
                Start Chat
              </Link>
            </div>

            {/* Mobile Menu Button */}
            <button
              onClick={() => setIsOpen(!isOpen)}
              className="md:hidden p-2 text-tejas hover:text-ojas transition-colors"
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
              className="md:hidden mt-4 pt-4 border-t border-border/30"
            >
              <div className="flex flex-col gap-4">
                {navLinks.map((link) => (
                  <a
                    key={link.href}
                    href={link.href}
                    onClick={() => setIsOpen(false)}
                    className="text-tejas/80 hover:text-ojas transition-colors"
                  >
                    {link.label}
                  </a>
                ))}
                <Link
                  to="/chat"
                  onClick={() => setIsOpen(false)}
                  className="px-5 py-2 bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-medium rounded-full text-center transition-all duration-300"
                >
                  Start Chat
                </Link>
              </div>
            </motion.div>
          )}
        </div>
      </div>
    </motion.nav>
  );
};
