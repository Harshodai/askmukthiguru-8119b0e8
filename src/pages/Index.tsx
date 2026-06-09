import { Navbar } from '@/components/landing/Navbar';
import { HeroSection } from '@/components/landing/HeroSection';
import { MeetTheGurusSection } from '@/components/landing/MeetTheGurusSection';
import { HowItWorksSection } from '@/components/landing/HowItWorksSection';
import { PracticesSection } from '@/components/landing/PracticesSection';
import { AboutMeditationSection } from '@/components/landing/AboutMeditationSection';
import { Footer } from '@/components/landing/Footer';
import { usePageMeta } from '@/hooks/usePageMeta';

const Index = () => {
  usePageMeta({
    title: 'AskMukthiGuru — AI Spiritual Guide',
    description: 'Discover inner peace through AI-guided conversations grounded in the teachings of Sri Preethaji and Sri Krishnaji. Free, private, and always available.',
    canonical: 'https://askmukthiguru.lovable.app/',
    ogImage: 'https://askmukthiguru.lovable.app/og-image.png',
    jsonLd: [
      {
        '@context': 'https://schema.org',
        '@type': 'Organization',
        name: 'AskMukthiGuru',
        url: 'https://askmukthiguru.lovable.app',
        logo: 'https://askmukthiguru.lovable.app/og-image.png',
        description: 'AI Spiritual Guide rooted in the teachings of Sri Preethaji & Sri Krishnaji from Ekam World School.',
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
              text: 'AskMukthiGuru is an AI-powered spiritual guide that answers questions based on the teachings of Sri Preethaji and Sri Krishnaji, founders of Ekam World School. It provides guidance on meditation, inner peace, and the Beautiful State.',
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
              text: 'Yes, AskMukthiGuru is free to access. You can have private, AI-guided spiritual conversations at any time, in multiple languages including English, Hindi, Telugu, and Malayalam.',
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

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <HeroSection />
      <MeetTheGurusSection />
      <HowItWorksSection />
      <PracticesSection />
      <AboutMeditationSection />
      <Footer />
    </div>
  );
};

export default Index;
