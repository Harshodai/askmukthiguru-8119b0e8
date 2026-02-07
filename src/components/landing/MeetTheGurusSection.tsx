import { motion } from 'framer-motion';
import { Heart, Sparkles } from 'lucide-react';
import gurusPhoto from '@/assets/gurus-photo.jpg';

export const MeetTheGurusSection = () => {
  return (
    <section id="gurus" className="py-24 relative overflow-hidden">
      {/* Background */}
      <div className="absolute inset-0 bg-celestial-gradient" />
      
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
            <span className="text-foreground">Meet Your</span>{' '}
            <span className="text-gradient-gold">Spiritual Guides</span>
          </h2>
          <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
            The wisdom of Sri Preethaji & Sri Krishnaji, founders of the Oneness Movement, 
            now accessible through a compassionate AI companion.
          </p>
        </motion.div>

        {/* Guru Card */}
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-50px' }}
          transition={{ duration: 0.7, delay: 0.2 }}
          className="max-w-4xl mx-auto"
        >
          <div className="glass-card-hover p-8 md:p-12 shadow-lg">
            <div className="flex flex-col md:flex-row gap-8 items-center">
              {/* Guru Photo */}
              <motion.div 
                className="relative"
                whileHover={{ scale: 1.02 }}
                transition={{ duration: 0.3 }}
              >
                <div className="w-40 h-40 md:w-48 md:h-48 rounded-full overflow-hidden ring-4 ring-ojas/30 shadow-xl relative">
                  <img
                    src={gurusPhoto}
                    alt="Sri Preethaji & Sri Krishnaji"
                    className="w-full h-full object-cover"
                  />
                  {/* Gradient overlay */}
                  <div className="absolute inset-0 bg-gradient-to-t from-background/10 to-transparent" />
                </div>
                <div className="absolute -top-2 -right-2 w-10 h-10 rounded-full bg-gradient-to-br from-ojas to-ojas-light flex items-center justify-center animate-pulse-glow shadow-md">
                  <Heart className="w-5 h-5 text-primary-foreground" />
                </div>
              </motion.div>

              {/* Content */}
              <div className="flex-1 text-center md:text-left">
                <h3 className="text-2xl md:text-3xl font-bold text-foreground mb-2">
                  Sri Preethaji & Sri Krishnaji
                </h3>
                <p className="text-ojas font-medium mb-4">
                  Founders of Ekam & The Oneness Movement
                </p>
                <p className="text-muted-foreground leading-relaxed mb-6">
                  For over three decades, Sri Preethaji and Sri Krishnaji have guided millions 
                  toward inner transformation. Their teachings focus on moving from a "suffering state" 
                  to a "beautiful state" through consciousness technology that blends ancient yogic 
                  wisdom with modern neuroscience.
                </p>
                
                {/* Key Teachings */}
                <div className="flex flex-wrap gap-3 justify-center md:justify-start">
                  {['Beautiful State', 'Consciousness', 'Inner Peace', 'Oneness'].map((tag) => (
                    <span
                      key={tag}
                      className="px-3 py-1 rounded-full text-sm bg-ojas/10 text-ojas border border-ojas/20 font-medium"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Teachings Quote */}
            <div className="mt-8 pt-8 border-t border-border">
              <div className="flex items-start gap-4">
                <Sparkles className="w-6 h-6 text-ojas flex-shrink-0 mt-1" />
                <blockquote className="text-lg italic text-foreground">
                  "When you are in a beautiful state, you become a blessing to everyone around you. 
                  Your very presence heals, your words inspire, and your actions create ripples of transformation."
                </blockquote>
              </div>
            </div>
          </div>
        </motion.div>

        {/* AI Disclosure */}
        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, delay: 0.5 }}
          className="text-center mt-8 text-sm text-muted-foreground"
        >
          <Heart className="w-4 h-4 inline mr-2 text-ojas" />
          Guided by their wisdom, powered by AI
        </motion.p>
      </div>
    </section>
  );
};
