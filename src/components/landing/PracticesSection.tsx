import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowRight, Clock, Flame, Heart, Moon, Sparkles } from 'lucide-react';
import { practices, type Practice } from '@/lib/practicesContent';

const iconFor: Record<Practice['slug'], typeof Flame> = {
  'soul-sync': Sparkles,
  'serene-mind': Flame,
  'beautiful-state': Heart,
  'daily-reflection': Moon,
};

export const PracticesSection = () => {
  return (
    <section id="practices" className="py-24 relative overflow-hidden">
      <div className="container mx-auto px-4 relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="text-center max-w-2xl mx-auto mb-12"
        >
          <h2 className="text-3xl sm:text-4xl font-bold text-gradient-gold mb-3">
            Daily practices
          </h2>
          <p className="text-muted-foreground">
            Guided meditations rooted in the teachings of Sri Preethaji & Sri Krishnaji.
            Pick the one that meets you today.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 max-w-6xl mx-auto">
          {practices.map((p, i) => {
            const Icon = iconFor[p.slug as Practice['slug']] ?? Sparkles;
            return (
              <motion.div
                key={p.slug}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.4, delay: i * 0.08 }}
              >
                <Link
                  to={`/practices/${p.slug}`}
                  className="glass-card-hover p-5 h-full flex flex-col group"
                >
                  <div className="w-11 h-11 rounded-xl bg-ojas/15 flex items-center justify-center mb-3">
                    <Icon className="w-5 h-5 text-ojas" />
                  </div>
                  <h3 className="font-semibold text-foreground">{p.title}</h3>
                  <p className="text-xs text-muted-foreground mt-1 flex-1">{p.tagline}</p>
                  <div className="flex items-center justify-between mt-4 text-[11px] text-muted-foreground">
                    <span className="inline-flex items-center gap-1">
                      <Clock className="w-3 h-3" /> {p.durationLabel}
                    </span>
                    <ArrowRight className="w-4 h-4 text-ojas group-hover:translate-x-0.5 transition-transform" />
                  </div>
                </Link>
              </motion.div>
            );
          })}
        </div>

        <div className="text-center mt-10">
          <Link
            to="/practices"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-medium shadow-md hover:scale-105 transition-transform"
          >
            Explore all practices <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    </section>
  );
};
