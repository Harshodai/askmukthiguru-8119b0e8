import { motion } from 'framer-motion';
import { Heart, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';

export const Footer = () => {
  return (
    <footer className="py-12 relative overflow-hidden border-t border-border bg-muted/30">
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
            <span className="text-xl font-bold text-gradient-gold">AskMukthiGuru</span>
          </motion.div>

          {/* Tagline */}
          <p className="text-muted-foreground text-sm mb-6 max-w-md">
            Your spiritual AI companion for discovering inner peace and the beautiful state.
          </p>

          {/* Links */}
          <div className="flex gap-6 mb-8">
            <Link to="/" className="text-sm text-muted-foreground hover:text-ojas transition-colors">
              Home
            </Link>
            <Link to="/chat" className="text-sm text-muted-foreground hover:text-ojas transition-colors">
              Chat
            </Link>
            <a href="#gurus" className="text-sm text-muted-foreground hover:text-ojas transition-colors">
              About
            </a>
          </div>

          {/* Disclaimer */}
          <div className="text-xs text-muted-foreground max-w-lg mb-6 bg-muted/50 rounded-lg p-3">
            <p>
              This is an AI companion trained on spiritual teachings. It is not a replacement 
              for medical or clinical therapy. If you are experiencing a mental health crisis, 
              please seek professional help.
            </p>
          </div>

          {/* Copyright */}
          <div className="flex items-center gap-1 text-sm text-muted-foreground">
            <span>Made with</span>
            <Heart className="w-4 h-4 text-ojas fill-ojas" />
            <span>for seekers everywhere</span>
          </div>
        </div>
      </div>
    </footer>
  );
};
