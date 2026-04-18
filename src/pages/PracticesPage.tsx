import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowRight, Clock, Sparkles, Flame, Heart, Moon } from 'lucide-react';
import { AppShell } from '@/components/layout/AppShell';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { practices, type Practice } from '@/lib/practicesContent';

const accentMap: Record<Practice['accent'], { icon: typeof Flame; ring: string; bg: string; text: string }> = {
  ojas: { icon: Sparkles, ring: 'ring-ojas/30', bg: 'bg-ojas/10', text: 'text-ojas' },
  prana: { icon: Moon, ring: 'ring-prana/30', bg: 'bg-prana/10', text: 'text-prana' },
  tejas: { icon: Flame, ring: 'ring-ojas/30', bg: 'bg-ojas/10', text: 'text-ojas-dark' },
  lotus: { icon: Heart, ring: 'ring-ojas-light/30', bg: 'bg-ojas-light/10', text: 'text-ojas-light' },
};

const PracticesPage = () => {
  return (
    <AppShell title="Practices">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6 sm:py-10">
        <motion.header
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="mb-8"
        >
          <h1 className="text-2xl sm:text-3xl font-semibold text-foreground">
            Daily practices
          </h1>
          <p className="text-sm sm:text-base text-muted-foreground mt-2 max-w-2xl">
            A small library of guided practices rooted in the teachings of
            Sri Preethaji & Sri Krishnaji. Choose one that meets you where you are today.
          </p>
        </motion.header>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-5">
          {practices.map((p, i) => {
            const A = accentMap[p.accent];
            return (
              <motion.div
                key={p.slug}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: i * 0.06 }}
              >
                <Link to={`/practices/${p.slug}`} className="block group">
                  <Card className={`h-full p-5 transition-all hover:shadow-lg ring-1 ${A.ring} hover:-translate-y-0.5`}>
                    <div className="flex items-start gap-4">
                      <div className={`w-11 h-11 rounded-xl ${A.bg} flex items-center justify-center shrink-0`}>
                        <A.icon className={`w-5 h-5 ${A.text}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-3">
                          <h3 className="font-semibold text-foreground truncate">
                            {p.title}
                          </h3>
                          <ArrowRight className="w-4 h-4 text-muted-foreground group-hover:text-ojas transition-colors shrink-0" />
                        </div>
                        <p className="text-sm text-muted-foreground mt-1">
                          {p.tagline}
                        </p>
                        <div className="flex flex-wrap gap-2 mt-3">
                          <Badge variant="secondary" className="gap-1">
                            <Clock className="w-3 h-3" /> {p.durationLabel}
                          </Badge>
                          {p.intentions.slice(0, 2).map((tag) => (
                            <Badge key={tag} variant="outline" className="text-[10px]">
                              {tag}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    </div>
                  </Card>
                </Link>
              </motion.div>
            );
          })}
        </div>
      </div>
    </AppShell>
  );
};

export default PracticesPage;
