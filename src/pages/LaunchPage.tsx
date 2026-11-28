import { Link } from 'react-router-dom';
import { motion, useReducedMotion } from 'framer-motion';
import { ArrowRight, BookOpen, Wind } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { PublicShell } from '@/components/layout/PublicShell';
import { Button } from '@/components/ui/button';
import { LaunchUpdatesSignup } from '@/components/guides/LaunchUpdatesSignup';
import { usePageMeta } from '@/hooks/usePageMeta';
import { buildCanonical } from '@/lib/domain';
import hero from '@/assets/hero-spiritual.webp';

export default function LaunchPage() {
  const { t } = useTranslation();
  const reduced = useReducedMotion();
  usePageMeta({ title: 'AskMukthiGuru — Spiritual Reflection & Meditation Guides', description: 'Start with spiritual guidance and a 3-minute Serene Mind practice. Explore sourced teaching guides and join AskMukthiGuru launch updates.', canonical: buildCanonical('/launch') });
  return (
    <PublicShell>
      <section className="relative isolate overflow-hidden border-b border-border">
        <img src={hero} alt="" className="absolute inset-0 -z-20 h-full w-full object-cover" />
        <div className="absolute inset-0 -z-10 bg-background/85" />
        <motion.div initial={reduced ? false : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45 }} className="mx-auto max-w-5xl px-6 py-14 sm:py-20 text-center">
          <img src="/images/askmukthiguru-3d-logo.webp" alt="" width={88} height={88} className="mx-auto mb-6 h-20 w-20 max-w-full rounded-full object-cover" />
          <p className="mb-4 text-sm font-medium text-ojas-ink dark:text-ojas">{t('launch.eyebrow', 'A moment for your inner life')}</p>
          <h1 className="break-words font-serif text-4xl font-semibold text-foreground sm:text-5xl">AskMukthiGuru</h1>
          <p className="mx-auto mt-5 max-w-xl text-lg leading-relaxed text-muted-foreground">{t('launch.intro', 'Spiritual reflection, recorded teachings, and a little room to breathe. Begin with a guide. Let your own inquiry lead.')}</p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Button asChild size="lg" className="h-auto min-h-11 max-w-full whitespace-normal py-3"><Link to="/guides/ai-spiritual-companion">{t('launch.primary', 'Read the spiritual guidance guide')}<ArrowRight className="ml-2 h-4 w-4 shrink-0" /></Link></Button>
            <Button asChild variant="outline" size="lg"><Link to="/guides/serene-mind-practice">{t('launch.secondary', 'Try a 3-minute practice')}</Link></Button>
          </div>
          <p className="mx-auto mt-6 max-w-lg text-sm text-muted-foreground">{t('launch.boundary', 'For reflection and personal practice. Not a replacement for a teacher, therapy, or professional care.')}</p>
        </motion.div>
      </section>
      <section className="mx-auto grid max-w-5xl gap-8 px-6 py-12 sm:grid-cols-2" aria-label={t('launch.guides', 'Begin here')}>
        <div className="space-y-3"><BookOpen className="h-6 w-6 text-ojas-ink dark:text-ojas" /><h2 className="font-serif text-2xl text-foreground">{t('launch.guidanceTitle', 'Spiritual guidance, with sources')}</h2><p className="leading-relaxed text-muted-foreground">{t('launch.guidanceBody', 'Explore what an AI spiritual guide can—and cannot—offer. Read about recorded teaching excerpts, reflection, and honest limits.')}</p><Button asChild variant="link" className="h-auto px-0"><Link to="/guides/ai-spiritual-companion">{t('launch.primary', 'Read the spiritual guidance guide')}<ArrowRight className="ml-2 h-4 w-4" /></Link></Button></div>
        <div className="space-y-3"><Wind className="h-6 w-6 text-ojas-ink dark:text-ojas" /><h2 className="font-serif text-2xl text-foreground">{t('launch.practiceTitle', 'Three minutes, one gentle pause')}</h2><p className="leading-relaxed text-muted-foreground">{t('launch.practiceBody', 'Read the Serene Mind guide, then choose a comfortable breathing practice. No need to force a feeling or rush a result.')}</p><Button asChild variant="link" className="h-auto px-0"><Link to="/guides/serene-mind-practice">{t('launch.secondary', 'Try a 3-minute practice')}<ArrowRight className="ml-2 h-4 w-4" /></Link></Button></div>
      </section>
      <div className="border-t border-border bg-muted/30"><div className="mx-auto max-w-xl px-6 py-12"><LaunchUpdatesSignup source="launch_page" /></div></div>
    </PublicShell>
  );
}
