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
    title: 'AskMukthiGuru — AI Spiritual Guide rooted in Preethaji & Krishnaji',
    description: 'Discover inner peace through AI-guided conversations grounded in the teachings of Sri Preethaji and Sri Krishnaji. Free, private, and always available.',
    canonical: 'https://askmukthiguru.lovable.app/',
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
