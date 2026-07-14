import { AppShell } from '@/components/layout/AppShell';
import { usePageMeta } from '@/hooks/usePageMeta';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';

const faqs = [
  {
    q: 'What exactly is the suffering state?',
    a: "It's a state of consciousness driven by fear, anger, jealousy, or the need to control outcomes, as described by Sri Preethaji & Sri Krishnaji. It shapes reactive thinking and decisions made from lack rather than clarity.",
  },
  {
    q: 'How is the Beautiful State different from just "staying positive"?',
    a: "Staying positive often means suppressing difficult feelings. The Beautiful State isn't forced positivity — it's a genuine shift in consciousness toward clarity and connection, which can hold difficulty without being consumed by it.",
  },
  {
    q: 'How quickly can I move from suffering state to Beautiful State?',
    a: 'Even a two to three minute breathing and attention-shifting practice can create a noticeable change. Consistent practice makes the shift faster and more stable over time.',
  },
  {
    q: 'Do I need meditation experience to try this?',
    a: 'No. The core steps — noticing your state, slowing your breath, and redirecting attention — require willingness more than prior experience.',
  },
  {
    q: 'What role does self-centric thinking play in the suffering state?',
    a: 'Self-centric thinking is often the engine of the suffering state — it keeps attention locked on personal fear and comparison. Recognizing this pattern is usually the first real step toward the Beautiful State.',
  },
];

const SufferingToBeautifulStatePage = () => {
  usePageMeta({
    title: 'Suffering State vs. Beautiful State: How to Shift',
    description:
      "Learn how to move from suffering state to beautiful state with practical steps rooted in Preethaji & Krishnaji's teachings.",
    canonical: 'https://askmukthiguru.lovable.app/guides/suffering-to-beautiful-state',
    ogType: 'article',
    jsonLd: {
      '@context': 'https://schema.org',
      '@graph': [
        {
          '@type': 'Article',
          headline: 'How to Move From Suffering State to Beautiful State',
          description:
            "A step-by-step path from the suffering state to the Beautiful State, grounded in Sri Preethaji & Sri Krishnaji's teachings.",
          author: { '@type': 'Organization', name: 'AskMukthiGuru' },
          mainEntityOfPage: 'https://askmukthiguru.lovable.app/guides/suffering-to-beautiful-state',
          keywords: 'suffering state, beautiful state, suffering state vs beautiful state, Preethaji Krishnaji',
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
    <AppShell title="Suffering to Beautiful State">
      <article className="mx-auto max-w-3xl px-4 py-10 space-y-8 text-foreground/90 leading-relaxed">
        <header className="space-y-3">
          <h1 className="text-3xl sm:text-4xl font-serif font-semibold text-foreground">
            How to Move From Suffering State to Beautiful State
          </h1>
          <p className="text-muted-foreground">
            Every day, without realizing it, we move between two broad states of consciousness — one driven by
            fear, comparison, and reactivity, and one marked by love, clarity, and connection. Sri Preethaji &amp;
            Sri Krishnaji call these the suffering state and the Beautiful State.
          </p>
        </header>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">The Core Difference</h2>
          <p>
            The suffering state is characterized by fear, anger, jealousy, or an urgent need to control outcomes.
            Thoughts move fast, the body tenses, and decisions come from a place of lack. The Beautiful State is
            different: a calmer, clearer, more connected quality of consciousness where thinking slows, warmth
            increases, and decisions come from clarity rather than urgency. Neither state is about ignoring real
            problems — it's about which inner state you solve them from.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Same Situation, Two Different States</h3>
          <p>
            Picture receiving critical feedback at work. From a suffering state, you might spiral into self-doubt
            or defensiveness. From the Beautiful State, the same feedback can be received with curiosity and even
            gratitude. The event doesn't change — your state does, and that changes everything about how you
            respond.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">Why We Default to the Suffering State</h2>
          <p>
            Most of us are trained, often since childhood, to run on self-centric thinking — a near-constant
            internal narration of what we lack, fear losing, or how we measure up to others. Learn more about{' '}
            <Link to="/guides/self-centric-thinking" className="text-ojas underline">
              how self-centric thinking keeps you in a suffering state
            </Link>{' '}
            and why simply "trying to be positive" rarely resolves it.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">A Step-by-Step Path</h2>
          <h3 className="text-lg font-semibold text-foreground">Step 1: Notice and Name the State</h3>
          <p>
            Before reacting, pause and ask, "Which state am I in right now?" Simply naming "suffering state"
            honestly, without shame, loosens its grip and creates a sliver of choice.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Step 2: Slow the Breath</h3>
          <p>
            The body and mind move together. Lengthening your breath to about 4 to 6 breaths per minute signals
            safety to your nervous system and makes a state shift physiologically possible.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Step 3: Practice Serene Mind</h3>
          <p>
            For a more structured reset, try{' '}
            <Link to="/guides/serene-mind-practice" className="text-ojas underline">
              the Serene Mind breathing practice
            </Link>
            , designed to quiet mental noise quickly so the Beautiful State has room to emerge.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Step 4: Redirect From Self to Connection</h3>
          <p>
            Suffering state thinking narrows focus to "me and my problem." Deliberately widen it: bring to mind
            someone you love, a moment of genuine connection, or simply the felt sense of being alive. Let feeling
            lead, not analysis.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Step 5: Choose the State Before the Action</h3>
          <p>
            Once you feel even a small shift, act from there. This is the essence of practicing{' '}
            <Link to="/guides/beautiful-state-meditation" className="text-ojas underline">
              Beautiful State meditation
            </Link>{' '}
            in daily life rather than only on a cushion.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold text-foreground">Why This Shift Takes Practice, Not Willpower</h2>
          <p>
            The suffering state has years of mental habit behind it, so expect resistance and days where the shift
            feels impossible. That's normal. The goal isn't permanent bliss — it's returning to clarity a little
            faster each time. Progress is measured in how quickly you notice the state, not in never falling into
            it.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold text-foreground">Making the Shift a Daily Habit</h2>
          <p>
            Small, repeated moments matter more than occasional big efforts. Use everyday triggers — a notification,
            a difficult message, a long queue — as reminders to check your state. You can{' '}
            <Link to="/practices" className="text-ojas underline">explore guided practices</Link> built specifically
            to help you build this awareness over time.
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
          <h2 className="text-xl font-semibold text-foreground">Start Shifting Your State Today</h2>
          <p>
            Reading about the shift is only the beginning — practicing it in real moments is where change happens.
            If you'd like a guided reflection to help you notice and shift your state right now, start a
            conversation.
          </p>
          <div className="flex flex-wrap gap-2 pt-2">
            <Button asChild><Link to="/chat">Start a conversation</Link></Button>
            <Button asChild variant="outline">
              <Link to="/guides/beautiful-state-meditation">Learn Beautiful State meditation</Link>
            </Button>
          </div>
        </section>
      </article>
    </AppShell>
  );
};

export default SufferingToBeautifulStatePage;
