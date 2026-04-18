import { Link, useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, Clock, ExternalLink, Headphones, PlayCircle } from 'lucide-react';
import { AppShell } from '@/components/layout/AppShell';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { getPracticeBySlug } from '@/lib/practicesContent';

const PracticeDetailPage = () => {
  const { slug = '' } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const practice = getPracticeBySlug(slug);

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
  const embedSrc = `https://www.youtube-nocookie.com/embed/${practice.videoId}?modestbranding=1&rel=0`;
  const watchUrl = `https://www.youtube.com/watch?v=${practice.videoId}`;
  const audioEmbed = practice.audioId
    ? `https://www.youtube-nocookie.com/embed/${practice.audioId}?modestbranding=1&rel=0`
    : null;
  const audioWatch = practice.audioId
    ? `https://www.youtube.com/watch?v=${practice.audioId}`
    : null;

  return (
    <AppShell title={practice.title}>
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
          <h1 className="text-2xl sm:text-3xl font-semibold text-foreground">
            {practice.title}
          </h1>
          <p className="text-sm sm:text-base text-muted-foreground mt-2">
            {practice.tagline}
          </p>
        </motion.header>

        {/* Video */}
        <Card className="overflow-hidden">
          <CardHeader className="flex-row items-center justify-between gap-3 space-y-0">
            <CardTitle className="flex items-center gap-2 text-base">
              <PlayCircle className="w-5 h-5 text-ojas" /> Guided video
            </CardTitle>
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
                title={`${practice.title} — guided video`}
                loading="lazy"
                allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                referrerPolicy="strict-origin-when-cross-origin"
              />
            </div>
          </CardContent>
        </Card>

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
                  title={`${practice.title} — audio`}
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
              {practice.purpose}
            </p>
          </CardContent>
        </Card>

        {/* How it works */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">How to do it</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="space-y-2 text-sm text-foreground/90 leading-relaxed list-decimal list-inside">
              {practice.howItWorks.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
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
