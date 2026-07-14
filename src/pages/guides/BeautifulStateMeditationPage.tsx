import { AppShell } from '@/components/layout/AppShell';
import { usePageMeta } from '@/hooks/usePageMeta';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';

const faqs = [
  {
    q: 'What is the Beautiful State in simple terms?',
    a: "The Beautiful State is a state of consciousness marked by love, clarity, and connectedness, described by Sri Preethaji & Sri Krishnaji as your natural condition beneath fear-driven, self-centric thinking. It's not a mood you manufacture, it's what remains when the noise of comparison and lack quiets down.",
  },
  {
    q: 'How long does it take to enter the Beautiful State?',
    a: "Even a 2 to 3 minute practice of slow breathing and shifting attention from self to connection can create a noticeable shift. Depth and consistency come with regular practice, but you don't need long sessions to begin feeling a difference.",
  },
  {
    q: "What's the difference between Beautiful State and just feeling happy?",
    a: "Happiness is often tied to circumstances going your way. The Beautiful State is more stable — a quality of consciousness, love, clarity, connectedness, that you can access even amid difficulty, because it doesn't depend on external outcomes.",
  },
  {
    q: 'Can I practice Beautiful State meditation without prior meditation experience?',
    a: 'Yes. The core practice involves slowing your breath, pausing before reacting, and redirecting attention toward connection rather than self-focused worry. It requires willingness more than experience.',
  },
  {
    q: 'How is Beautiful State related to Serene Mind practice?',
    a: 'Serene Mind is a specific breathing-based technique that helps quiet the noise of the mind quickly, often used as a doorway into the Beautiful State. Practicing Serene Mind regularly makes it easier to recognize and return to the Beautiful State throughout your day.',
  },
];

const BeautifulStateMeditationPage = () => {
  usePageMeta({
    title: 'How to Enter Beautiful State: A Meditation Guide',
    description:
      "Learn how to enter the Beautiful State through simple meditation. Practical steps rooted in Preethaji & Krishnaji's teachings.",
    canonical: 'https://askmukthiguru.lovable.app/guides/beautiful-state-meditation',
    ogType: 'article',
    jsonLd: {
      '@context': 'https://schema.org',
      '@graph': [
        {
          '@type': 'Article',
          headline: 'How to Enter Beautiful State: A Practical Meditation Guide',
          description:
            "A step-by-step guide to entering the Beautiful State through breath, attention, and connection — grounded in Sri Preethaji & Sri Krishnaji's teachings.",
          author: { '@type': 'Organization', name: 'AskMukthiGuru' },
          mainEntityOfPage: 'https://askmukthiguru.lovable.app/guides/beautiful-state-meditation',
          keywords: 'beautiful state meditation, how to enter beautiful state, Preethaji Krishnaji, spiritual meditation',
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
    <AppShell title="Beautiful State Meditation">
      <article className="mx-auto max-w-3xl px-4 py-10 space-y-8 text-foreground/90 leading-relaxed">
        <header className="space-y-3">
          <h1 className="text-3xl sm:text-4xl font-serif font-semibold text-foreground">
            How to Enter Beautiful State: A Practical Meditation Guide
          </h1>
          <p className="text-muted-foreground">
            Most of us move between anxiety, comparison, and a vague sense of not-enough. The Beautiful State, as
            taught by Sri Preethaji &amp; Sri Krishnaji, is different — a state of consciousness marked by love,
            connectedness, and clarity that's available right now, underneath the noise.
          </p>
        </header>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">What the Beautiful State Really Is</h2>
          <p>
            The Beautiful State is your natural condition when you are not caught in self-centric thinking — the
            constant inner narration of what you lack, what you fear losing, or how you compare to others. When that
            inner noise quiets, what remains is a felt sense of ease, warmth toward yourself and others, and a mind
            that is clear rather than reactive. It's not about forcing positivity. It's about removing the layers
            of thought that keep you from your own baseline peace.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Beautiful State vs. Suffering State</h3>
          <p>
            Preethaji &amp; Krishnaji often contrast this with the Suffering State — where the mind is driven by
            fear, anger, jealousy, or the need to control outcomes. The first step toward the Beautiful State is
            simply noticing which state is running your thoughts and decisions at any given moment.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">A Step-by-Step Practice</h2>
          <h3 className="text-lg font-semibold text-foreground">Step 1: Pause and Name the State</h3>
          <p>
            Before reacting to a stressful email, conversation, or thought, pause for a breath. Ask honestly, "Am I
            in a suffering state right now?" Naming it takes away some of its grip.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Step 2: Use the Breath to Shift</h3>
          <p>
            Slow your breathing to roughly 4 to 6 breaths per minute. Lengthen the inhale and exhale until your
            nervous system downshifts. A calmer body makes a calmer mind possible.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Step 3: Redirect Attention from Self to Connection</h3>
          <p>
            Self-centric thinking narrows your focus to "me and my problem." Gently widen your attention. Bring to
            mind someone you love, or a moment when you felt genuinely connected to another person or to life
            itself. Let the feeling, not the thought, lead.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Step 4: Ask a Different Question</h3>
          <p>
            Instead of "How do I fix this problem," try "What would love do here?" or "What state do I want to
            create in this moment?" This shifts you from reactive problem-solving to conscious state-creation.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Step 5: Let the State Lead Your Action</h3>
          <p>
            Once you feel even a small shift toward calm and warmth, act from there. Send the reply, have the
            conversation, or make the decision from that steadier place rather than from urgency or fear.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">A 3-Minute Meditation You Can Do Anywhere</h2>
          <ul className="list-disc pl-6 space-y-2">
            <li><strong>Minute 1:</strong> Sit comfortably. Slow your breath to 4–6 counts in, 4–6 counts out.</li>
            <li><strong>Minute 2:</strong> Bring to mind a person or memory that genuinely opens your heart. Stay with the feeling, not the story around it.</li>
            <li><strong>Minute 3:</strong> Silently ask, "What state do I want to carry into the next hour?" Let an answer arise without forcing one.</li>
          </ul>
          <p>
            This short practice works well before a difficult meeting, after an argument, or first thing in the
            morning before your mind fills with tasks.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold text-foreground">Why It's Harder Than It Sounds</h2>
          <p>
            Entering the Beautiful State is simple in instruction but not always easy in practice, because the mind
            has years of momentum in self-centric thinking. Expect resistance and days when it feels impossible.
            The practice is not about permanent bliss — it's about returning, a little faster each time, to that
            inner clarity. Consistency matters more than duration.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold text-foreground">Bringing This Into Daily Life</h2>
          <p>
            The real test isn't how calm you feel while meditating, but how you show up in traffic, in a hard
            conversation, or when plans fall apart. Use small triggers — an inbox notification, a red light, a
            moment of waiting — as reminders to pause and check your state. For structured support, you can{' '}
            <Link to="/practices" className="text-ojas underline">browse guided practices</Link> built around the
            Beautiful State and Serene Mind, or{' '}
            <Link to="/guides/ai-spiritual-companion" className="text-ojas underline">
              explore the AI Spiritual Companion
            </Link>{' '}
            for guided reflection between sessions.
          </p>
        </section>

        <section className="space-y-4">
          <h2 className="text-xl font-semibold text-foreground">Frequently asked questions</h2>
          <dl className="space-y-4">
            {faqs.map((f) => (
              <div key={f.q} className="space-y-1">
                <dt className="font-semibold text-foreground">{f.q}</dt>
                <dd>{f.a}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="space-y-3 rounded-lg border border-border/60 bg-card/60 p-6">
          <h2 className="text-xl font-semibold text-foreground">Ready to Practice with Support?</h2>
          <p>
            Reading is a start; the real shift happens in practice and reflection. If you'd like to talk through
            what's coming up for you, or want a guided question to sit with today, start a conversation now.
          </p>
          <div className="flex flex-wrap gap-2 pt-2">
            <Button asChild><Link to="/chat">Start a conversation</Link></Button>
            <Button asChild variant="outline"><Link to="/guides/serene-mind-practice">Learn Serene Mind</Link></Button>
          </div>
        </section>
      </article>
    </AppShell>
  );
};

export default BeautifulStateMeditationPage;
