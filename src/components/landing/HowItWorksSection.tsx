import { motion } from 'framer-motion';
import { MessageCircle, Heart, Sparkles, Flower } from 'lucide-react';

const steps = [
  {
    icon: MessageCircle,
    title: 'Start a Conversation',
    description: 'Begin your journey by sharing what\'s on your mind or in your heart with our AI companion.',
  },
  {
    icon: Heart,
    title: 'Share Your Heart',
    description: 'Express your thoughts, feelings, struggles, or questions in a safe, judgment-free space.',
  },
  {
    icon: Sparkles,
    title: 'Receive Wisdom',
    description: 'Get personalized guidance rooted in the profound teachings of Sri Preethaji & Sri Krishnaji.',
  },
  {
    icon: Flower,
    title: 'Experience Serenity',
    description: 'When needed, be guided through the Serene Mind meditation to shift from suffering to peace.',
  },
];

export const HowItWorksSection = () => {
  return (
    <section id="how-it-works" className="py-24 relative overflow-hidden bg-spiritual-gradient">
      {/* Decorative elements */}
      <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-ojas/30 to-transparent" />
      <div className="absolute bottom-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-prana/30 to-transparent" />

      <div className="relative z-10 container mx-auto px-6">
        {/* Section Header */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-100px' }}
          transition={{ duration: 0.7 }}
          className="text-center mb-16"
        >
          <h2 className="text-4xl md:text-5xl font-bold mb-4">
            <span className="text-tejas">How It</span>{' '}
            <span className="text-gradient-gold">Works</span>
          </h2>
          <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
            A simple journey from wherever you are to your beautiful state
          </p>
        </motion.div>

        {/* Steps Grid */}
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 max-w-6xl mx-auto">
          {steps.map((step, index) => (
            <motion.div
              key={step.title}
              initial={{ opacity: 0, y: 40 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-50px' }}
              transition={{ duration: 0.5, delay: index * 0.15 }}
            >
              <div className="glass-card-hover p-6 h-full text-center group">
                {/* Step Number */}
                <div className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-ojas/20 text-ojas text-sm font-bold mb-4">
                  {index + 1}
                </div>

                {/* Icon */}
                <div className="relative w-16 h-16 mx-auto mb-4">
                  <div className="absolute inset-0 rounded-full bg-gradient-to-br from-ojas/20 to-prana/20 group-hover:scale-110 transition-transform duration-300" />
                  <div className="relative w-full h-full flex items-center justify-center">
                    <step.icon className="w-8 h-8 text-ojas group-hover:text-ojas-light transition-colors duration-300" />
                  </div>
                </div>

                {/* Content */}
                <h3 className="text-lg font-semibold text-tejas mb-2">{step.title}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{step.description}</p>
              </div>
            </motion.div>
          ))}
        </div>

        {/* Connection Line (Desktop) */}
        <div className="hidden lg:block absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-3/4 h-px bg-gradient-to-r from-transparent via-ojas/20 to-transparent pointer-events-none" />
      </div>
    </section>
  );
};
