import { motion } from 'framer-motion';
import { Flame, Clock, Calendar, Wind } from 'lucide-react';
import { getMeditationStats } from '@/lib/meditationStorage';

export const MeditationStats = () => {
  const stats = getMeditationStats();

  const statItems = [
    {
      icon: Flame,
      value: stats.totalSessions,
      label: 'Sessions',
      color: 'text-ojas',
      bgColor: 'bg-ojas/10',
    },
    {
      icon: Clock,
      value: stats.totalMinutes,
      label: 'Minutes',
      color: 'text-prana',
      bgColor: 'bg-prana/10',
    },
    {
      icon: Calendar,
      value: stats.streakDays,
      label: 'Day Streak',
      color: 'text-ojas-dark',
      bgColor: 'bg-ojas-dark/10',
    },
    {
      icon: Wind,
      value: stats.totalCycles,
      label: 'Breaths',
      color: 'text-prana-light',
      bgColor: 'bg-prana/10',
    },
  ];

  if (stats.totalSessions === 0) {
    return (
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card p-4 mb-4"
      >
        <div className="text-center">
          <Flame className="w-8 h-8 text-ojas mx-auto mb-2" />
          <h3 className="font-semibold text-foreground">Begin Your Journey</h3>
          <p className="text-sm text-muted-foreground mt-1">
            Try the Serene Mind meditation to start tracking your progress
          </p>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-4 mb-4"
    >
      <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
        <Flame className="w-4 h-4 text-ojas" />
        Your Soul Journey
      </h3>
      
      <div className="grid grid-cols-4 gap-2">
        {statItems.map((item, index) => (
          <motion.div
            key={item.label}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: index * 0.1 }}
            className="text-center"
          >
            <div className={`w-10 h-10 rounded-full ${item.bgColor} flex items-center justify-center mx-auto mb-1`}>
              <item.icon className={`w-4 h-4 ${item.color}`} />
            </div>
            <motion.p 
              className="text-lg font-bold text-foreground"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: index * 0.1 + 0.2 }}
            >
              {item.value}
            </motion.p>
            <p className="text-xs text-muted-foreground">{item.label}</p>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
};
