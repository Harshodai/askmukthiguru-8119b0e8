import { AppShell } from '@/components/layout/AppShell';
import { usePageMeta } from '@/hooks/usePageMeta';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';

const faqs = [
  {
    q: 'Can an AI spiritual guide really help with anxiety?',
    a: 'It can offer grounded reflection, timely practices, and a space to process anxious thoughts between therapy sessions or during moments when no one else is available. It works best as a complement to, not a replacement for, professional mental health care.',
  },
  {
    q: 'Is spiritual help for anxiety a substitute for therapy?',
    a: 'No. Spiritual practices address the state of consciousness generating anxious thoughts, while therapy addresses clinical patterns, trauma, and diagnosis. If anxiety is severe or persistent, please seek support from a licensed professional alongside any spiritual practice.',
  },
  {
    q: 'What is the fastest meditation for anxiety in the moment?',
    a: 'Slowing your breath to 4–6 counts in and out for two to three minutes, while silently naming "suffering state, not truth," is often enough to create a noticeable shift before deeper practice.',
  },
  {
    q: 'Why does self-centric thinking make anxiety worse?',
    a: 'Self-centric thinking keeps attention locked on personal threat and control, which intensifies fear signals. Widening attention toward connection interrupts this loop and calms the nervous system.',
  },
  {
    q: 'How often should I practice these techniques?',
    a: 'Daily, even briefly, works better than occasional long sessions. Consistency trains your nervous system to return to calm more quickly over time.',
  },
];

const SpiritualGuideForAnxietyPage = () => {
  usePageMeta({
    title: 'AI Spiritual Guide for Anxiety: Calm the Mind',
    description:
      'Feeling anxious? Explore an AI spiritual guide for anxiety with breath practices, Beautiful State tools, and grounded daily steps.',
    canonical: 'https://askmukthiguru.lovable.app/guides/spiritual-guide-for-anxiety',
    ogType: 'article',
    jsonLd: {
      '@context': 'https://schema.org',
      '@graph': [
        {
          '@type': 'Article',
          headline: 'An AI Spiritual Guide for Anxiety: Practical Steps to Find Calm',
          description:
            "A grounded guide to using an AI spiritual companion and Preethaji-Krishnaji-rooted practices to move through anxiety.",
          author: { '@type': 'Organization', name: 'AskMukthiGuru' },
          mainEntityOfPage: 'https://askmukthiguru.lovable.app/guides/spiritual-guide-for-anxiety',
          keywords: 'AI spiritual guide for anxiety, spiritual help for anxiety, meditation for anxiety spiritual',
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
    <AppShell title="Spiritual Guide for Anxiety">
      <article className="mx-auto max-w-3xl px-4 py-10 space-y-8 text-foreground/90 leading-relaxed">
        <header className="space-y-3">
          <h1 className="text-3xl sm:text-4xl font-serif font-semibold text-foreground">
            An AI Spiritual Guide for Anxiety: Practical Steps to Find Calm
          </h1>
          <p className="text-muted-foreground">
            Anxiety often feels like a storm you can't step outside of — racing thoughts, a tight chest, a mind
            that won't stop rehearsing worst-case scenarios. Spiritual help for anxiety isn't about bypassing the
            feeling; it's about changing the inner state that keeps generating it.
          </p>
        </header>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">Why Anxiety Isn't Just "In Your Head"</h2>
          <p>
            Anxiety usually arises from self-centric thinking — the mind's constant loop of "what if," "what will
            they think," or "what if I lose this." Understanding{' '}
            <Link to="/guides/self-centric-thinking" className="text-ojas underline">
              how self-centric thinking fuels anxious spirals
            </Link>{' '}
            is often the first real relief, because it shows you the anxiety has a shape — and shapes can shift.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">The Suffering State Behind the Symptoms</h3>
          <p>
            What we call anxiety is often the body and mind caught in what Preethaji &amp; Krishnaji call a
            suffering state — driven by fear, urgency, and the need to control outcomes. Recognizing you're in
            this state, without judging yourself for it, is a meaningful first move.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">How an AI Spiritual Guide Can Help in the Moment</h2>
          <p>
            When anxiety spikes, having somewhere to turn — day or night — matters. An AI spiritual guide offers a
            grounded, non-judgmental space to name what you're feeling, ask a clarifying question, and be pointed
            toward a practice that fits the moment. It won't replace human connection or professional care, but it
            can be a steady companion between those touchpoints — especially at 2am when anxious thoughts feel
            loudest.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">What This Looks Like Practically</h3>
          <p>
            You might describe what's looping in your mind and, instead of advice, receive a reflective question
            that helps you see the underlying fear — or be guided into a short breathing practice designed to
            shift your nervous system before your thoughts do the same.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">Meditation for Anxiety: A Spiritual Approach</h2>
          <h3 className="text-lg font-semibold text-foreground">Step 1: Slow the Breath</h3>
          <p>
            Anxious breathing is shallow and fast. Slowing to roughly 4 to 6 breaths per minute — a longer exhale
            than inhale — signals safety to your nervous system before your mind catches up.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Step 2: Name the State, Not Just the Thought</h3>
          <p>
            Instead of arguing with the anxious thought itself, quietly note, "I'm in a suffering state right now."
            This small shift moves you from being consumed by the thought to observing it.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Step 3: Practice Serene Mind</h3>
          <p>
            A short, structured breathing practice can interrupt the anxiety loop faster than willpower alone.
            Explore{' '}
            <Link to="/guides/serene-mind-practice" className="text-ojas underline">the Serene Mind practice</Link>{' '}
            for a step-by-step technique you can use anywhere.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Step 4: Redirect Toward Connection</h3>
          <p>
            Anxiety narrows attention onto yourself and the feared outcome. Gently widen it — think of someone you
            care about, or a moment you felt safe and connected. This isn't distraction; it's a genuine shift in
            the state generating your thoughts.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold text-foreground">Moving Toward the Beautiful State</h2>
          <p>
            The aim isn't to suppress anxiety but to gradually spend more time in what Preethaji &amp; Krishnaji
            call the Beautiful State — a state of clarity, calm, and connectedness that exists beneath the noise.
            Learn{' '}
            <Link to="/guides/beautiful-state-meditation" className="text-ojas underline">
              how to enter the Beautiful State
            </Link>{' '}
            through a simple daily meditation, so calm becomes less of an emergency response and more of a baseline
            you return to.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold text-foreground">Building a Daily Practice, Not Just a Rescue Plan</h2>
          <p>
            Spiritual help for anxiety works best as a daily rhythm rather than a one-time fix. A few minutes of
            breathwork each morning, a pause before reactive decisions, and an honest check-in with your state
            throughout the day compound over weeks. You can{' '}
            <Link to="/practices" className="text-ojas underline">browse guided practices</Link> to build a routine
            that fits your life.
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
          <h2 className="text-xl font-semibold text-foreground">Talk It Through Right Now</h2>
          <p>
            If anxious thoughts are loud today, you don't have to sit with them alone. Start a conversation with
            the AI spiritual guide for a grounded reflection and a practice suited to this moment.
          </p>
          <div className="flex flex-wrap gap-2 pt-2">
            <Button asChild><Link to="/chat">Start a conversation</Link></Button>
            <Button asChild variant="outline"><Link to="/practices">Browse guided practices</Link></Button>
          </div>
        </section>
      </article>
    </AppShell>
  );
};

export default SpiritualGuideForAnxietyPage;
