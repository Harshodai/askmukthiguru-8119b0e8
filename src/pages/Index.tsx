import { Navbar } from '@/components/landing/Navbar';
import { HeroSection } from '@/components/landing/HeroSection';
import { MeetTheGurusSection } from '@/components/landing/MeetTheGurusSection';
import { HowItWorksSection } from '@/components/landing/HowItWorksSection';
import { PracticesSection } from '@/components/landing/PracticesSection';
import { AboutMeditationSection } from '@/components/landing/AboutMeditationSection';
import { Footer } from '@/components/landing/Footer';

const Index = () => {
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
