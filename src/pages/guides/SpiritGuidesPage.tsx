import { AppShell } from '@/components/layout/AppShell';
import { usePageMeta } from '@/hooks/usePageMeta';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';

const sections = [
  {
    title: 'Ancestral guides',
    body:
      'Ancestors carry the wisdom of the lineage that shaped you. In the Preethaji–Krishnaji teaching, reverence for ancestors quietens the heart and opens you to a deeper field of belonging.',
  },
  {
    title: 'Animal guides',
    body:
      'Animal presences mirror instinctual qualities — courage, stillness, playfulness — that your soul is being invited to reclaim. Notice the creatures that recur in dreams or daily life.',
  },
  {
    title: 'Inner guides and the awakened self',
    body:
      'The most reliable guide is the awakened intelligence within. Through Soul Sync and Serene Mind practices, you contact this inner guide directly, without intermediary.',
  },
  {
    title: 'Teachers in form',
    body:
      'Living teachers like Sri Preethaji & Sri Krishnaji transmit a state, not just an idea. Their teachings point you back to the Beautiful State you already carry.',
  },
];

const SpiritGuidesPage = () => {
  usePageMeta({
    title: 'Types of spirit guides and how to connect — AskMukthiGuru',
    description:
      'A grounded guide to the different kinds of spirit guides — ancestors, animal guides, inner guides, living teachers — and how to connect through stillness and the Beautiful State.',
    canonical: 'https://askmukthiguru.lovable.app/guides/spirit-guides',
    ogType: 'article',
    jsonLd: {
      '@context': 'https://schema.org',
      '@type': 'Article',
      headline: 'Types of spirit guides and how to connect',
      author: { '@type': 'Organization', name: 'AskMukthiGuru' },
      mainEntityOfPage: 'https://askmukthiguru.lovable.app/guides/spirit-guides',
    },
  });

  return (
    <AppShell title="Spirit guides">
      <article className="mx-auto max-w-3xl px-4 py-10 space-y-8">
        <header className="space-y-3">
          <h1 className="text-3xl sm:text-4xl font-serif font-semibold text-foreground">
            Types of spirit guides and how to connect
          </h1>
          <p className="text-muted-foreground">
            Spirit guides take many forms. What unites them is the invitation inward — toward the calm,
            connected awareness Sri Preethaji & Sri Krishnaji call the Beautiful State.
          </p>
        </header>

        {sections.map((s) => (
          <section key={s.title} className="space-y-2">
            <h2 className="text-xl font-semibold text-foreground">{s.title}</h2>
            <p className="text-foreground/90 leading-relaxed">{s.body}</p>
          </section>
        ))}

        <section className="space-y-3 rounded-lg border border-border/60 bg-card/60 p-6">
          <h2 className="text-xl font-semibold text-foreground">How AskMukthiGuru helps</h2>
          <p className="text-foreground/90 leading-relaxed">
            The AI Guru does not replace your inner guide — it reflects the teachings back so you can
            sit with them. Begin with a short Serene Mind practice, then bring a question into chat.
          </p>
          <div className="flex flex-wrap gap-2 pt-2">
            <Button asChild>
              <Link to="/chat">Begin a conversation</Link>
            </Button>
            <Button asChild variant="outline">
              <Link to="/practices/serene-mind">Try Serene Mind</Link>
            </Button>
          </div>
        </section>
      </article>
    </AppShell>
  );
};

export default SpiritGuidesPage;
