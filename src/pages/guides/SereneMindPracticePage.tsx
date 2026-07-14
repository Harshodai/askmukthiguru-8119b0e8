import { AppShell } from '@/components/layout/AppShell';
import { usePageMeta } from '@/hooks/usePageMeta';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';

const faqs = [
  {
    q: 'What is Serene Mind meditation?',
    a: "Serene Mind is a short breathing-based meditation practice from Sri Preethaji & Sri Krishnaji's teachings that slows your breath to about 4 to 6 breaths per minute, helping calm the nervous system and quiet reactive thinking in just a few minutes.",
  },
  {
    q: 'Can a 3-minute meditation really reduce stress?',
    a: 'Yes. Slowing your breathing rate for even a few minutes shifts your body out of a stress response by increasing heart rate variability and signaling safety to the nervous system. Consistency matters more than length.',
  },
  {
    q: 'How often should I practice Serene Mind?',
    a: "Ideally several short sessions throughout the day rather than one long session. Practicing during calm moments — not just during crises — builds the skill so it's easier to access when real stress hits.",
  },
  {
    q: "What if my mind won't quiet down during the practice?",
    a: "That's normal and expected. The goal isn't a blank mind — it's a calmer body and a slightly looser grip on anxious thoughts. Focus on the breath and body sensations rather than forcing thoughts away.",
  },
  {
    q: 'Is Serene Mind the same as Beautiful State?',
    a: "They're related but distinct. Serene Mind is a specific breath practice that calms the mind, often serving as a doorway into the Beautiful State — a broader state of love, clarity, and connectedness.",
  },
];

const SereneMindPracticePage = () => {
  usePageMeta({
    title: 'Serene Mind Meditation: A 3-Minute Stress Practice',
    description:
      'A simple serene mind meditation to calm stress in 3 minutes. Learn the breath technique and when to use it, step by step.',
    canonical: 'https://askmukthiguru.lovable.app/guides/serene-mind-practice',
    ogType: 'article',
    jsonLd: {
      '@context': 'https://schema.org',
      '@graph': [
        {
          '@type': 'Article',
          headline: 'Serene Mind Meditation: A 3-Minute Practice for Stress',
          description:
            'A step-by-step Serene Mind breathing practice from Sri Preethaji & Sri Krishnaji to calm stress and reset the nervous system in three minutes.',
          author: { '@type': 'Organization', name: 'AskMukthiGuru' },
          mainEntityOfPage: 'https://askmukthiguru.lovable.app/guides/serene-mind-practice',
          keywords: 'serene mind meditation, 3 minute meditation stress, breath practice, Preethaji Krishnaji',
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
    <AppShell title="Serene Mind Practice">
      <article className="mx-auto max-w-3xl px-4 py-10 space-y-8 text-foreground/90 leading-relaxed">
        <header className="space-y-3">
          <h1 className="text-3xl sm:text-4xl font-serif font-semibold text-foreground">
            Serene Mind Meditation: A 3-Minute Practice for Stress
          </h1>
          <p className="text-muted-foreground">
            Stress shows up as a tight chest before a meeting, a racing mind at 2am, or irritability with people
            you love. Serene Mind — taught by Sri Preethaji &amp; Sri Krishnaji — is designed to interrupt that
            stress response quickly, using breath and attention rather than willpower.
          </p>
        </header>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">What Is Serene Mind?</h2>
          <p>
            Serene Mind is a breathing-based technique that slows your breath rate to roughly 4 to 6 breaths per
            minute. At this pace, your nervous system shifts out of a stress response into a calmer, regulated
            state. Physiologically, slower breathing increases heart rate variability and signals safety to the
            body. Spiritually, it creates the internal quiet needed to step out of self-centric thinking.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Why Breath Rate Matters</h3>
          <p>
            Most people breathe 12 to 20 times a minute — faster still under stress. Deliberately slowing this is
            one of the fastest ways to change your internal state without needing special conditions or equipment.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">The 3-Minute Practice, Step by Step</h2>
          <h3 className="text-lg font-semibold text-foreground">Step 1: Find a Still Point (20 seconds)</h3>
          <p>
            Sit or stand with your spine reasonably upright. You do not need silence — a parked car, a bathroom
            stall, or your desk chair all work.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Step 2: Slow the Inhale and Exhale (90 seconds)</h3>
          <p>
            Breathe in slowly for a count of 5, and out for 5 to 6. Don't strain. If 5 feels too long, start at 4
            and build up over days. Keep this rhythm for about ten to fifteen rounds.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Step 3: Soften the Body (30 seconds)</h3>
          <p>
            With each exhale, consciously release tension from your jaw, shoulders, and hands. This is often where
            the sharpest change in feeling happens — the body leads the mind into calm.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Step 4: Widen Awareness (40 seconds)</h3>
          <p>
            Instead of following the same anxious thought loop, gently notice sounds around you, the temperature of
            the air, or a simple point of gratitude. This interrupts the mental story fueling the stress.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Step 5: Set an Intention</h3>
          <p>
            Before opening your eyes, silently decide how you want to move into the next task — calm, clear,
            patient. This turns the practice from an escape into something that shapes your next actions.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold text-foreground">When to Use Serene Mind</h2>
          <ul className="list-disc pl-6 space-y-1">
            <li>Before a difficult conversation or meeting</li>
            <li>When you notice racing thoughts or a tight chest</li>
            <li>Right after waking, before checking your phone</li>
            <li>Before responding to a triggering message or email</li>
            <li>During a work break, as a reset instead of scrolling</li>
          </ul>
          <p>
            The goal isn't to save this for a crisis. Used regularly during ordinary moments, it becomes far more
            effective when real stress hits, because your body already knows the pattern.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">Common Mistakes</h2>
          <h3 className="text-lg font-semibold text-foreground">Forcing the Breath</h3>
          <p>Straining to hit a specific count creates more tension. Adjust to what feels sustainable.</p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Expecting Instant Silence</h3>
          <p>Thoughts don't disappear in three minutes. The aim is to loosen their grip, not achieve a blank mind.</p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Only Using It in Emergencies</h3>
          <p>
            Practicing only when overwhelmed makes it harder to access in the moment. Regular short sessions build
            the skill so it's available when you need it most.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold text-foreground">A Doorway to Deeper Practice</h2>
          <p>
            Serene Mind is often a starting point that opens into the{' '}
            <Link to="/guides/beautiful-state-meditation" className="text-ojas underline">Beautiful State</Link> — a
            broader practice of stepping out of self-centric thinking into connectedness and clarity. You can{' '}
            <Link to="/practices" className="text-ojas underline">find more guided practices</Link> to build on this
            foundation, or{' '}
            <Link to="/guides/ai-spiritual-companion" className="text-ojas underline">
              learn how an AI companion can guide daily practice
            </Link>{' '}
            between sessions.
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
          <h2 className="text-xl font-semibold text-foreground">Practice With Guidance</h2>
          <p>
            If stress feels like more than a passing moment, or you want help identifying what's actually driving
            it, talk it through for a guided reflection tailored to what you're facing right now.
          </p>
          <div className="flex flex-wrap gap-2 pt-2">
            <Button asChild><Link to="/chat">Talk it through in chat</Link></Button>
            <Button asChild variant="outline"><Link to="/practices">Explore all practices</Link></Button>
          </div>
        </section>
      </article>
    </AppShell>
  );
};

export default SereneMindPracticePage;
