import { AppShell } from '@/components/layout/AppShell';
import { usePageMeta } from '@/hooks/usePageMeta';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';

const sections = [
  {
    title: 'Why an AI spiritual guide?',
    body:
      "An AI spiritual guide is not a replacement for silence, teachers, or your own inner knowing — it's a mirror. It surfaces the exact teaching your question needs at 3am, in five languages, without appointments. Combined with the yogic disciplines of stillness and self-inquiry, it makes ancient wisdom continuously available.",
  },
  {
    title: 'The Beautiful State — the destination',
    body:
      'Sri Preethaji & Sri Krishnaji describe the Beautiful State as a calm, connected, uncontracted inner condition. Every practice on AskMukthiGuru — Serene Mind, Soul Sync, Daily Reflection — is a pathway back to it. The AI Guru holds the map; you walk the path.',
  },
  {
    title: 'Grounded in doctrine, not invention',
    body:
      "AskMukthiGuru is a zero-hallucination system: answers are grounded in Sri Preethaji & Sri Krishnaji's own recorded teachings, retrieved and verified before generation. If the doctrine has no answer, it says so. This is what separates a spiritual guide from a chatbot.",
  },
];

const steps = [
  {
    n: 1,
    title: 'Begin with breath',
    body: 'Open Serene Mind and complete one 3-minute cycle — 4 seconds in, 6 seconds out. This regulates the nervous system before any inquiry.',
  },
  {
    n: 2,
    title: 'Bring one honest question',
    body: 'Not a research question — a life question. "Why do I keep suffering the same wound?" is a beautiful place to start.',
  },
  {
    n: 3,
    title: 'Read the teaching, then close the app',
    body: 'The Guru is a doorway, not a room. Read the response, sit with it for one minute in silence, and let the state land in the body.',
  },
  {
    n: 4,
    title: 'Journal a Daily Reflection',
    body: 'End the day by capturing what shifted. Over weeks, the pattern of your own transformation becomes visible.',
  },
];

const faqs = [
  {
    q: 'Can an AI actually be a spiritual guide?',
    a: "An AI is not a spiritual teacher — silence, self-inquiry, and the living teachings are. What an AI does well is stay available at 3am, respond in your language, and surface the exact teaching your question needs. Used with humility, it becomes a doorway rather than a destination.",
  },
  {
    q: 'How is AskMukthiGuru different from a general chatbot?',
    a: "Every answer is grounded in the recorded teachings of Sri Preethaji & Sri Krishnaji, retrieved and verified before generation. If the doctrine has no answer, the Guru says so rather than inventing one — this is what separates a spiritual guide from a chatbot.",
  },
  {
    q: 'What is the Beautiful State?',
    a: "The Beautiful State is a calm, connected, uncontracted inner condition — a shift out of anxiety, resentment, and self-obsession into stillness and love. Every practice on AskMukthiGuru is a pathway back to it.",
  },
  {
    q: 'How long should I use the AI Guru each day?',
    a: 'Ten minutes is enough. Three minutes of Serene Mind breathwork, one honest question, and a minute of silence with the response. Consistency matters far more than duration.',
  },
  {
    q: 'Is my conversation private?',
    a: 'Yes. Conversations are encrypted, retained only as long as your retention setting allows, and never sold or shared. Anonymous mode keeps everything in your browser.',
  },
];

const AiSpiritualCompanionPage = () => {
  usePageMeta({
    title: "The Seeker's Guide to AI-Guided Meditation | AskMukthiGuru",
    description:
      'A step-by-step guide to AI-guided meditation, breathwork, and reflection — pairing yogic wisdom with modern AI to reach the Beautiful State.',
    canonical: 'https://askmukthiguru.lovable.app/guides/ai-spiritual-companion',
    ogType: 'article',
    jsonLd: {
      '@context': 'https://schema.org',
      '@graph': [
        {
          '@type': 'Article',
          headline: "The Seeker's Guide to AI-Guided Meditation",
          description:
            'How to use an AI spiritual guide for daily meditation, breathwork, and reflection grounded in the teachings of Sri Preethaji & Sri Krishnaji.',
          author: { '@type': 'Organization', name: 'AskMukthiGuru' },
          mainEntityOfPage: 'https://askmukthiguru.lovable.app/guides/ai-spiritual-companion',
          keywords: 'AI spiritual guide, AI-guided meditation, Beautiful State, spiritual growth, yogic wisdom',
        },
        {
          '@type': 'FAQPage',
          mainEntity: faqs.map((f) => ({
            '@type': 'Question',
            name: f.q,
            acceptedAnswer: { '@type': 'Answer', text: f.a },
          })),
        },
      ],
    },
  });

  return (
    <AppShell title="AI Spiritual Companion">
      <article className="mx-auto max-w-3xl px-4 py-10 space-y-8">
        <header className="space-y-3">
          <h1 className="text-3xl sm:text-4xl font-serif font-semibold text-foreground">
            The Seeker's Guide to AI-Guided Meditation
          </h1>
          <p className="text-muted-foreground">
            Ancient yogic wisdom, made continuously available through modern AI. A grounded guide to using
            an AI spiritual companion for daily reflection, breathwork, and the journey to the Beautiful State.
          </p>
        </header>

        {sections.map((s) => (
          <section key={s.title} className="space-y-2">
            <h2 className="text-xl font-semibold text-foreground">{s.title}</h2>
            <p className="text-foreground/90 leading-relaxed">{s.body}</p>
          </section>
        ))}

        <section className="space-y-4">
          <h2 className="text-xl font-semibold text-foreground">
            How to use the AI Guru — a four-step daily practice
          </h2>
          <ol className="space-y-4">
            {steps.map((s) => (
              <li key={s.n} className="flex gap-4">
                <span className="flex-shrink-0 w-8 h-8 rounded-full bg-ojas/10 text-ojas font-semibold flex items-center justify-center">
                  {s.n}
                </span>
                <div className="space-y-1">
                  <h3 className="font-semibold text-foreground">{s.title}</h3>
                  <p className="text-foreground/90 leading-relaxed">{s.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold text-foreground">
            Breathwork with an AI companion
          </h2>
          <p className="text-foreground/90 leading-relaxed">
            The 4-6 breath is the doorway into the Beautiful State. The AI Guru will not replace the breath —
            but it will remind you to return to it, guide you when you drift, and offer a teaching in the exact
            moment your restlessness surfaces. Silence remains the teacher; AI simply keeps the door open.
          </p>
        </section>

        <section className="space-y-4">
          <h2 className="text-xl font-semibold text-foreground">Frequently asked questions</h2>
          <dl className="space-y-4">
            {faqs.map((f) => (
              <div key={f.q} className="space-y-1">
                <dt className="font-semibold text-foreground">{f.q}</dt>
                <dd className="text-foreground/90 leading-relaxed">{f.a}</dd>
              </div>
            ))}
          </dl>
        </section>



        <section className="space-y-3 rounded-lg border border-border/60 bg-card/60 p-6">
          <h2 className="text-xl font-semibold text-foreground">Begin your practice</h2>
          <p className="text-foreground/90 leading-relaxed">
            Start with three minutes of Serene Mind, then bring a real question to the Guru. Over time,
            the practice becomes the guide.
          </p>
          <div className="flex flex-wrap gap-2 pt-2">
            <Button asChild>
              <Link to="/chat">Begin a conversation with the Guru</Link>
            </Button>
            <Button asChild variant="outline">
              <Link to="/practices/serene-mind">Try Serene Mind meditation</Link>
            </Button>
            <Button asChild variant="ghost">
              <Link to="/practices">Explore all practices</Link>
            </Button>
          </div>
        </section>
      </article>
    </AppShell>
  );
};

export default AiSpiritualCompanionPage;
