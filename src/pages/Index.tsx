import { Capacitor } from '@capacitor/core';
import { Navbar } from '@/components/landing/Navbar';
import { HeroSection } from '@/components/landing/HeroSection';
import { MeetTheGurusSection } from '@/components/landing/MeetTheGurusSection';
import { HowItWorksSection } from '@/components/landing/HowItWorksSection';
import { PracticesSection } from '@/components/landing/PracticesSection';
import { WisdomGraphPreview } from '@/components/landing/WisdomGraphPreview';
import { SampleWisdomSection } from '@/components/landing/SampleWisdomSection';
import { AboutMeditationSection } from '@/components/landing/AboutMeditationSection';
import { SafetyPillarsSection } from '@/components/landing/SafetyPillarsSection';
import { Footer } from '@/components/landing/Footer';
import { GoogleOneTap } from '@/components/common/GoogleOneTap';
import { usePageMeta } from '@/hooks/usePageMeta';
import { useChatCapabilities } from '@/hooks/useChatCapabilities';
import { useTranslation } from 'react-i18next';
import { PRODUCTION_DOMAIN, PRODUCTION_OG_IMAGE, PRODUCTION_ICON, buildCanonical } from '@/lib/domain';

const Index = () => {
  usePageMeta({
    title: 'AskMukthiGuru — Spiritual Reflection and Guided Practice',
    description: 'Bring a question, pause with a guided practice, and return to teaching-grounded spiritual reflection inspired by Sri Preethaji and Sri Krishnaji.',
    canonical: buildCanonical('/'),
    ogImage: PRODUCTION_OG_IMAGE,
    jsonLd: [
      {
        '@context': 'https://schema.org',
        '@type': 'Organization',
        name: 'AskMukthiGuru',
        url: PRODUCTION_DOMAIN,
        logo: PRODUCTION_ICON,
        description: 'An AI companion for spiritual reflection and guided practice, inspired by the teachings of Sri Preethaji and Sri Krishnaji.',
        sameAs: ['https://www.ekam.org'],
      },
      {
        '@context': 'https://schema.org',
        '@type': 'FAQPage',
        mainEntity: [
          {
            '@type': 'Question',
            name: 'What is AskMukthiGuru?',
            acceptedAnswer: {
              '@type': 'Answer',
              text: 'AskMukthiGuru is an AI companion for spiritual reflection inspired by the teachings of Sri Preethaji and Sri Krishnaji. Visitors can bring a question, choose a guided practice, and return to personal reflection at their own pace. It is not medical, clinical, therapeutic, or emergency care.',
            },
          },
          {
            '@type': 'Question',
            name: 'What is the Beautiful State?',
            acceptedAnswer: {
              '@type': 'Answer',
              text: 'The Beautiful State is a concept taught by Sri Preethaji & Sri Krishnaji — a state of inner peace, love, and connection that exists beyond suffering. It is our natural state when we are free from disconnection.',
            },
          },
          {
            '@type': 'Question',
            name: 'Is AskMukthiGuru free to use?',
            acceptedAnswer: {
              '@type': 'Answer',
              text: 'Yes, AskMukthiGuru is free to access. You can begin with an AI-guided spiritual conversation or a short practice, and use the privacy information on this site to decide what to share.',
            },
          },
          {
            '@type': 'Question',
            name: 'What is Serene Mind Meditation?',
            acceptedAnswer: {
              '@type': 'Answer',
              text: 'Serene Mind is a 3-minute guided breathwork and meditation practice within AskMukthiGuru, designed to quickly calm the mind and bring you into a state of clarity and peace.',
            },
          },
        ],
      },
    ],
  });

  const isNative = Capacitor.isNativePlatform();
  const { capabilities } = useChatCapabilities();

  return (
    <div className="min-h-dvh bg-background">
      {!isNative && capabilities.googleSso && <GoogleOneTap />}
      <Navbar />
      <HeroSection />
      <MeetTheGurusSection />
      <HowItWorksSection />
      <PracticesSection />
      <WisdomGraphPreview />
      <SampleWisdomSection />
      <AboutMeditationSection />
      <SafetyPillarsSection />
      <Footer />
    </div>
  );
};

export default Index;
