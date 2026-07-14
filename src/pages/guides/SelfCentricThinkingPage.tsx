import { AppShell } from '@/components/layout/AppShell';
import { usePageMeta } from '@/hooks/usePageMeta';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';

const faqs = [
  {
    q: 'What does self-centric thinking mean spiritually?',
    a: 'Self-centric thinking refers to the mind\'s default habit of filtering everything through "how does this affect me" — fear of loss, comparison, and the need for control. Sri Preethaji & Sri Krishnaji teach it as the root of much everyday suffering and overthinking.',
  },
  {
    q: 'How do I stop overthinking without just distracting myself?',
    a: "Instead of distraction, notice the self-centric pattern driving the thoughts, ask what fear it's protecting, and deliberately widen your focus toward connection or a bigger question. Combining this with slow breathing interrupts the loop at both the mental and physical level.",
  },
  {
    q: 'Is self-centric thinking the same as selfishness?',
    a: "No. Self-centric thinking is a mental habit, not a character flaw. It's the mind's tendency to loop everything back to self-protection, self-image, and comparison — something almost everyone experiences, not a sign of being a bad person.",
  },
  {
    q: 'What is the alternative to self-centric thinking?',
    a: "Preethaji & Krishnaji describe an alternative often called connection-centric or consciousness-centric thinking — where attention naturally widens to include others' wellbeing and a bigger perspective, rather than being consumed entirely by self-focused concerns.",
  },
  {
    q: 'Can breathing really help with overthinking?',
    a: 'Yes. Overthinking is often paired with shallow, rapid breathing tied to stress. Slowing the breath to around 4 to 6 breaths per minute calms the nervous system and creates space for clearer, less reactive thinking.',
  },
];

const SelfCentricThinkingPage = () => {
  usePageMeta({
    title: 'Self-Centric Thinking: How to Stop Overthinking',
    description:
      'Understand self-centric thinking and learn a spiritual, practical approach to stop overthinking and find real clarity.',
    canonical: 'https://askmukthiguru.lovable.app/guides/self-centric-thinking',
    ogType: 'article',
    jsonLd: {
      '@context': 'https://schema.org',
      '@graph': [
        {
          '@type': 'Article',
          headline: 'Self-Centric Thinking: A Spiritual Approach to Stop Overthinking',
          description:
            "A grounded guide to self-centric thinking — what it is, why it drives overthinking, and how to shift toward connection-centric awareness. Rooted in Sri Preethaji & Sri Krishnaji's teachings.",
          author: { '@type': 'Organization', name: 'AskMukthiGuru' },
          mainEntityOfPage: 'https://askmukthiguru.lovable.app/guides/self-centric-thinking',
          keywords: 'self centric thinking, stop overthinking spiritually, Preethaji Krishnaji, suffering state',
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
    <AppShell title="Self-Centric Thinking">
      <article className="mx-auto max-w-3xl px-4 py-10 space-y-8 text-foreground/90 leading-relaxed">
        <header className="space-y-3">
          <h1 className="text-3xl sm:text-4xl font-serif font-semibold text-foreground">
            Self-Centric Thinking: A Spiritual Approach to Stop Overthinking
          </h1>
          <p className="text-muted-foreground">
            Overthinking rarely feels like a choice. It feels like the mind running on its own — replaying
            conversations, rehearsing worst-case scenarios, calculating what others think of you. Sri Preethaji
            &amp; Sri Krishnaji describe this pattern as self-centric thinking.
          </p>
        </header>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">What Is Self-Centric Thinking?</h2>
          <p>
            Self-centric thinking is the mind's habitual focus on "me" — my image, my security, my comparisons, my
            losses, my fears. It is not the same as selfishness in the everyday sense. It's the default operating
            mode of most human minds, shaped by survival instincts and social conditioning, where nearly every
            thought loops back to how something affects the self.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">How It Shows Up</h3>
          <ul className="list-disc pl-6 space-y-1">
            <li>Replaying a conversation, worrying about how you were perceived</li>
            <li>Comparing your life, career, or relationships to others</li>
            <li>Catastrophizing about the future and what you might lose</li>
            <li>Needing to be right, validated, or in control of outcomes</li>
            <li>Feeling resentment when things don't go your way</li>
          </ul>
          <p>
            None of this makes you a bad person. It makes you human. But left unchecked, this pattern becomes the
            engine of chronic overthinking and low-grade suffering.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">Why It Fuels Overthinking</h2>
          <p>
            Overthinking is what happens when the mind keeps trying to protect or improve the self and can't find
            resolution. Because self-centric thinking is inherently anxious — focused on threat, lack, and
            comparison — it generates endless "what if" and "what does this mean about me" loops. The mind isn't
            broken; it's doing exactly what a self-focused lens trains it to do.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">The Trap of Thinking Your Way Out</h3>
          <p>
            Most people try to solve overthinking by thinking harder. But since the thinking itself is
            self-centric, more of it usually deepens the loop. The way out isn't more analysis — it's a shift in
            the underlying state of mind.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-foreground">A Spiritual, Practical Approach</h2>
          <h3 className="text-lg font-semibold text-foreground">Step 1: Notice the Pattern Without Judgment</h3>
          <p>
            The first move isn't to stop the thoughts — it's to notice them. Silently name it: "This is
            self-centric thinking." Naming creates a small but real distance between you and the thought loop.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Step 2: Ask What the Thought Is Protecting</h3>
          <p>
            Behind most overthinking is a fear: rejection, failure, loss of control, being seen as inadequate. Ask,
            "What am I afraid this means about me?" Often, simply naming the fear reduces its intensity.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Step 3: Shift from Self to Connection</h3>
          <p>
            Self-centric thinking narrows focus onto "me." Deliberately widen it. Think of someone you can help
            today, or bring to mind a moment of genuine connection. This isn't distraction — it's retraining the
            mind's default direction.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Step 4: Use the Breath to Interrupt the Loop</h3>
          <p>
            Overthinking is often paired with shallow, quick breathing. Slowing your breath to around 4 to 6
            breaths a minute for a couple of minutes physically interrupts the anxious loop and makes space for
            clearer thought.
          </p>
          <h3 className="text-lg font-semibold text-foreground pt-2">Step 5: Ask a Bigger Question</h3>
          <p>
            Instead of "How do I fix this," try "What would I do here if I weren't afraid," or "What matters most
            beyond my own image." Bigger questions pull the mind out of the narrow self-centric loop.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold text-foreground">What Replaces Self-Centric Thinking</h2>
          <p>
            Preethaji &amp; Krishnaji describe the alternative as consciousness-centric or connection-centric
            thinking — where your attention naturally includes the wellbeing of others and the bigger picture, not
            just your own image and outcomes. This isn't about erasing your needs; it's about no longer being ruled
            entirely by them. From this wider state, the same problems often look smaller and more workable.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold text-foreground">Building a Daily Practice</h2>
          <p>
            Pair a short breathing practice each morning with a brief evening reflection: "Where did self-centric
            thinking run my day, and where did I catch it?" Over weeks, this builds real self-awareness rather than
            a quick fix. You can{' '}
            <Link to="/practices" className="text-ojas underline">explore guided practices</Link> that support this
            shift, learn the{' '}
            <Link to="/guides/serene-mind-practice" className="text-ojas underline">Serene Mind breath</Link>, or{' '}
            <Link to="/guides/ai-spiritual-companion" className="text-ojas underline">
              read about the AI Spiritual Companion
            </Link>{' '}
            for support noticing your own patterns day to day.
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
          <h2 className="text-xl font-semibold text-foreground">When You're Stuck Right Now</h2>
          <p>
            If you're in the middle of an overthinking spiral, you don't have to work through it alone. Bring your
            thoughts in for a grounded, guided reflection that can help you see the pattern and find your way back
            to clarity.
          </p>
          <div className="flex flex-wrap gap-2 pt-2">
            <Button asChild><Link to="/chat">Bring your thoughts into chat</Link></Button>
            <Button asChild variant="outline"><Link to="/guides/beautiful-state-meditation">Learn the Beautiful State</Link></Button>
          </div>
        </section>
      </article>
    </AppShell>
  );
};

export default SelfCentricThinkingPage;
