import { useEffect, useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, Clock, ExternalLink, Headphones, PlayCircle, Star, Share2, Check } from 'lucide-react';
import { AppShell } from '@/components/layout/AppShell';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { getPracticeBySlug, getLocalizedPractice } from '@/lib/practicesContent';
import { useFavorites } from '@/hooks/useFavorites';
import { recordRecentPractice } from '@/lib/favoritesStorage';
import { cn } from '@/lib/utils';
import { WisdomReflectionPractice } from '@/components/meditation/WisdomReflectionPractice';
import { usePageMeta } from '@/hooks/usePageMeta';
import { useToast } from '@/hooks/use-toast';
import { useTranslation } from 'react-i18next';

const PracticeDetailPage = () => {
  const { slug = '' } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const practice = getPracticeBySlug(slug);
  const { isFavorited, toggle } = useFavorites();
  const { toast } = useToast();
  const { t, i18n } = useTranslation();
  // Localised copy for rendering; base `practice` remains canonical English for
  // SEO meta + JSON-LD (which must be language-neutral at server-render time).
  const lp = practice ? getLocalizedPractice(practice, t, i18n.language) : practice;

  const fav = practice ? isFavorited(practice.slug) : false;
  const [shareCopied, setShareCopied] = useState(false);

  // Track this as the most recently opened practice for the landing "Continue" card.
  useEffect(() => {
    if (practice) recordRecentPractice(practice.slug);
  }, [practice]);

  usePageMeta({
    title: practice ? `${practice.title} | AskMukthiGuru` : 'Practice not found | AskMukthiGuru',
    description: practice ? `${practice.purpose.slice(0, 155)}` : 'The requested practice could not be found.',
    canonical: practice ? `https://askmukthiguru.lovable.app/practices/${practice.slug}` : 'https://askmukthiguru.lovable.app/practices',
    ogType: practice ? 'article' : 'website',
    ogImage: 'https://askmukthiguru.lovable.app/og-image.png',
    jsonLd: practice
      ? {
          '@context': 'https://schema.org',
          '@type': 'HowTo',
          name: practice.title,
          description: practice.purpose,
          totalTime: practice.durationLabel,
          step: practice.howItWorks.map((text, i) => ({
            '@type': 'HowToStep',
            position: i + 1,
            text,
          })),
        }
      : undefined,
  });

  if (!practice) {
    return (
      <AppShell title="Practice not found">
        <div className="max-w-2xl mx-auto px-4 py-16 text-center space-y-4">
          <h2 className="text-xl font-semibold text-foreground">
            We couldn't find that practice
          </h2>
          <Button onClick={() => navigate('/practices')}>
            <ArrowLeft className="w-4 h-4 mr-2" /> Back to practices
          </Button>
        </div>
      </AppShell>
    );
  }

  // Build sandboxed embed URL — no autoplay, modest branding, no related videos from other channels.
  const embedSrc = practice.videoId ? `https://www.youtube-nocookie.com/embed/${practice.videoId}?modestbranding=1&rel=0` : null;
  const watchUrl = practice.videoId ? `https://www.youtube.com/watch?v=${practice.videoId}` : null;
  const audioEmbed = practice.audioId
    ? `https://www.youtube-nocookie.com/embed/${practice.audioId}?modestbranding=1&rel=0`
    : null;
  const audioWatch = practice.audioId
    ? `https://www.youtube.com/watch?v=${practice.audioId}`
    : null;

  const handleShare = async () => {
    const stepsText = lp!.howItWorks.map((step, idx) => `${idx + 1}. ${step}`).join('\n');
    const benefitsText = lp!.benefits.map((b) => `• ${b}`).join('\n');
    const mediaText = watchUrl ? `\n\n🎥 *Guided Video:* ${watchUrl}` : '';
    const shareText = `🧘 *${lp!.title}* — ${lp!.tagline} (${lp!.durationLabel})\n\n📖 *How to Practice:*\n${stepsText}\n\n✨ *Key Benefits:*\n${benefitsText}${mediaText}\n\nShared via AskMukthiGuru`;
    
    try {
      await navigator.clipboard.writeText(shareText);
      setShareCopied(true);
      toast({
        title: 'Meditation Guide Copied!',
        description: 'The steps and benefits are copied to your clipboard to share with others.',
      });
      setTimeout(() => setShareCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy to clipboard: ', err);
      toast({
        title: 'Unable to copy link',
        description: 'Please copy the steps manually from the page.',
        variant: 'destructive',
      });
    }
  };

  return (
    <AppShell title={lp!.title}>
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 sm:py-10 space-y-6">
        <Link
          to="/practices"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-ojas transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> All practices
        </Link>

        <motion.header
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <Badge variant="secondary" className="gap-1">
              <Clock className="w-3 h-3" /> {practice.durationLabel}
            </Badge>
            {practice.intentions.map((tag) => (
              <Badge key={tag} variant="outline">
                {tag}
              </Badge>
            ))}
          </div>
          <div className="flex items-start justify-between gap-3">
            <h1 className="text-2xl sm:text-3xl font-semibold text-foreground">
              {lp!.title}
            </h1>
            <div className="flex gap-2 shrink-0">
              <Button
                variant="outline"
                size="sm"
                onClick={handleShare}
                className="gap-1.5"
              >
                {shareCopied ? (
                  <>
                    <Check className="w-4 h-4 text-emerald-500" />
                    <span className="hidden sm:inline">Copied!</span>
                  </>
                ) : (
                  <>
                    <Share2 className="w-4 h-4 text-muted-foreground" />
                    <span className="hidden sm:inline">Share guide</span>
                  </>
                )}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  toggle(practice.slug);
                  toast({
                    title: fav ? 'Removed from favorites' : 'Added to favorites',
                    description: `${practice.title} has been ${fav ? 'removed from' : 'added to'} your list.`,
                  });
                }}
                aria-pressed={fav}
                className="gap-1.5"
              >
                <Star className={cn('w-4 h-4', fav ? 'fill-ojas text-ojas' : 'text-muted-foreground')} />
                <span className="hidden sm:inline">{fav ? 'Favorited' : 'Add to favorites'}</span>
              </Button>
            </div>
          </div>
          <p className="text-sm sm:text-base text-muted-foreground mt-2">
            {lp!.tagline}
          </p>
        </motion.header>

        {practice.format === 'source-reflection' ? <WisdomReflectionPractice /> : embedSrc && watchUrl && (
        <Card className="overflow-hidden">
          <CardHeader className="flex-row items-center justify-between gap-3 space-y-0">
            <h2 className="flex items-center gap-2 text-base font-semibold leading-none tracking-tight">
              <PlayCircle className="w-5 h-5 text-ojas" /> Guided video
            </h2>
            <Button asChild variant="outline" size="sm" className="gap-1.5">
              <a href={watchUrl} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Open in YouTube</span>
                <span className="sm:hidden">YouTube</span>
              </a>
            </Button>
          </CardHeader>
          <CardContent>
            <div className="relative w-full overflow-hidden rounded-lg bg-muted" style={{ paddingTop: '56.25%' }}>
              <iframe
                className="absolute inset-0 w-full h-full"
                src={embedSrc}
                title={`${lp!.title} — guided video`}
                loading="lazy"
                allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                referrerPolicy="strict-origin-when-cross-origin"
              />
            </div>
          </CardContent>
        </Card>
        )}

        {/* Optional audio */}
        {audioEmbed && audioWatch && (
          <Card className="overflow-hidden">
            <CardHeader className="flex-row items-center justify-between gap-3 space-y-0">
              <CardTitle className="flex items-center gap-2 text-base">
                <Headphones className="w-5 h-5 text-prana" /> Audio version
              </CardTitle>
              <Button asChild variant="outline" size="sm" className="gap-1.5">
                <a href={audioWatch} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Open in YouTube</span>
                  <span className="sm:hidden">YouTube</span>
                </a>
              </Button>
            </CardHeader>
            <CardContent>
              <div className="relative w-full overflow-hidden rounded-lg bg-muted" style={{ paddingTop: '25%' }}>
                <iframe
                  className="absolute inset-0 w-full h-full"
                  src={audioEmbed}
                  title={`${lp!.title} — audio`}
                  loading="lazy"
                  allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                  referrerPolicy="strict-origin-when-cross-origin"
                />
              </div>
            </CardContent>
          </Card>
        )}

        {/* Purpose */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Why this practice</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-foreground/90 leading-relaxed">
              {lp!.purpose}
            </p>
          </CardContent>
        </Card>

        {/* How it works */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">How to do it</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="space-y-4 text-sm text-foreground/90 leading-relaxed list-decimal list-inside">
              {lp!.howItWorks.map((step) => {
                const parts = step.split(': ');
                if (parts.length > 1) {
                  return (
                    <li key={step} className="align-text-top">
                      <span className="font-semibold text-foreground">{parts[0]}:</span> {parts.slice(1).join(': ')}
                    </li>
                  );
                }
                return <li key={step}>{step}</li>;
              })}
            </ol>
          </CardContent>
        </Card>

        {/* Key Benefits */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Key Benefits</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3 text-sm text-foreground/90 leading-relaxed list-disc list-inside">
              {lp!.benefits.map((benefit) => {
                const parts = benefit.split(': ');
                if (parts.length > 1) {
                  return (
                    <li key={benefit}>
                      <span className="font-semibold text-foreground">{parts[0]}:</span> {parts.slice(1).join(': ')}
                    </li>
                  );
                }
                return <li key={benefit}>{benefit}</li>;
              })}
            </ul>
          </CardContent>
        </Card>

        {practice.inApp && (
          <div className="flex justify-end">
            <Button asChild className="bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground">
              <Link to={practice.inApp.path}>{practice.inApp.label}</Link>
            </Button>
          </div>
        )}
      </div>
    </AppShell>
  );
};

export default PracticeDetailPage;
