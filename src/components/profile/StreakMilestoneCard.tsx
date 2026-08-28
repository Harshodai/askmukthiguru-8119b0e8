import React from 'react';
import { motion } from 'framer-motion';
import { Flame, Award, Sparkles, Shield, Compass, Heart, Lock } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';

export interface MilestoneBadge {
  id: string;
  name: string;
  sanskritName: string;
  requiredDays: number;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  unlocked: boolean;
  unlockedAt?: string;
}

interface StreakMilestoneCardProps {
  currentStreak: number;
  longestStreak: number;
  nextMilestoneDays?: number;
}

export const SACRED_MILESTONES: Omit<MilestoneBadge, 'unlocked'>[] = [
  {
    id: 'awakening_spark',
    name: 'Awakening Spark',
    sanskritName: 'Prarambha',
    requiredDays: 3,
    description: 'Broke the cycle of inertia; ignited three continuous days of contemplative awareness.',
    icon: Sparkles,
  },
  {
    id: 'serene_mind_master',
    name: '7-Day Serene Mind Master',
    sanskritName: 'Shanta Manas',
    requiredDays: 7,
    description: 'Stabilized the vagus nerve and calmed the thought-storm through 7 days of pranayama.',
    icon: Flame,
  },
  {
    id: 'witnessing_presence',
    name: 'Witnessing Presence',
    sanskritName: 'Sakshi Bhava',
    requiredDays: 14,
    description: 'Established the witness self capable of observing reactive emotions without identifying.',
    icon: Compass,
  },
  {
    id: 'deeksha_sadhak',
    name: '21-Day Deeksha Sadhak',
    sanskritName: 'Deeksha Sadhana',
    requiredDays: 21,
    description: 'Rewired neural pathways into persistent Beautiful State through three weeks of sadhana.',
    icon: Heart,
  },
  {
    id: 'transformation_tapasya',
    name: 'Transformation Tapasya',
    sanskritName: 'Tapasya Siddhi',
    requiredDays: 40,
    description: 'Completed a sacred mandala of 40 days of unbroken spiritual contemplation.',
    icon: Shield,
  },
  {
    id: 'mukthi_luminary',
    name: 'Mukthi Luminary',
    sanskritName: 'Mukthi Jnani',
    requiredDays: 108,
    description: 'Attained supreme consistency; 108 days living from unshakeable inner freedom.',
    icon: Award,
  },
];

export const StreakMilestoneCard: React.FC<StreakMilestoneCardProps> = ({
  currentStreak = 0,
  longestStreak = 0,
}) => {
  const milestones: MilestoneBadge[] = SACRED_MILESTONES.map((m) => ({
    ...m,
    unlocked: currentStreak >= m.requiredDays,
  }));

  const nextMilestone = milestones.find((m) => !m.unlocked) || milestones[milestones.length - 1];
  const prevMilestone = [...milestones].reverse().find((m) => m.unlocked);
  const baseDays = prevMilestone ? prevMilestone.requiredDays : 0;
  const progressPercent = nextMilestone.unlocked
    ? 100
    : Math.min(100, Math.max(0, ((currentStreak - baseDays) / (nextMilestone.requiredDays - baseDays)) * 100));

  return (
    <div className="rounded-3xl border border-saffron-gold/30 bg-gradient-to-br from-card via-card to-saffron-gold/5 p-6 shadow-sm space-y-6">
      {/* Top Banner with Glowing Flame */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          {/* Animated 3D Flame Avatar */}
          <div className="relative flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-tr from-amber-600 via-saffron-gold to-yellow-400 p-0.5 shadow-lg shadow-saffron-gold/20">
            <motion.div
              animate={{
                scale: [1, 1.15, 0.95, 1.08, 1],
                rotate: [0, 2, -2, 1, 0],
              }}
              transition={{
                duration: 3.5,
                repeat: Infinity,
                ease: 'easeInOut',
              }}
              className="w-full h-full rounded-2xl bg-zinc-950 flex flex-col items-center justify-center"
            >
              <Flame className="w-8 h-8 text-saffron-gold fill-saffron-gold/30 animate-pulse" />
            </motion.div>
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span className="text-3xl font-serif font-bold tracking-tight text-foreground">
                {currentStreak}
              </span>
              <span className="text-xs font-semibold uppercase tracking-wider text-saffron-gold">
                Days Unbroken Sadhana
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Longest streak: <span className="font-semibold text-foreground">{longestStreak} days</span>
            </p>
          </div>
        </div>

        {/* Milestone Progress Mini-Bar */}
        <div className="w-full sm:w-64 space-y-2 rounded-2xl bg-background/50 border border-border/40 p-3">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground font-medium">Next: {nextMilestone.name}</span>
            <span className="font-mono text-saffron-gold font-semibold">
              {currentStreak}/{nextMilestone.requiredDays}d
            </span>
          </div>
          <Progress value={progressPercent} className="h-1.5 bg-muted/60" />
        </div>
      </div>

      {/* Milestone Badges Carousel / Grid */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
            <Award className="w-3.5 h-3.5 text-saffron-gold" /> Sacred Milestone Badges
          </h4>
          <span className="text-xs font-mono text-saffron-gold">
            {milestones.filter((m) => m.unlocked).length} / {milestones.length} Unlocked
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
          {milestones.map((m) => {
            const Icon = m.icon;
            return (
              <motion.div
                key={m.id}
                whileHover={{ y: -3, scale: 1.02 }}
                className={`relative group rounded-2xl border p-3.5 flex flex-col items-center text-center space-y-2 transition-all ${
                  m.unlocked
                    ? 'bg-gradient-to-b from-saffron-gold/15 to-card border-saffron-gold/40 shadow-sm'
                    : 'bg-card/40 border-border/40 opacity-55'
                }`}
              >
                <div
                  className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                    m.unlocked
                      ? 'bg-saffron-gold/20 text-saffron-gold shadow-[0_0_12px_rgba(234,179,8,0.3)]'
                      : 'bg-muted text-muted-foreground'
                  }`}
                >
                  {m.unlocked ? <Icon className="w-5 h-5" /> : <Lock className="w-4 h-4" />}
                </div>

                <div className="space-y-0.5 min-w-0 w-full">
                  <p className="text-xs font-semibold font-serif text-foreground truncate">{m.name}</p>
                  <p className="text-[10px] font-mono text-saffron-gold/80 italic">{m.sanskritName}</p>
                  <p className="text-[10px] text-muted-foreground">{m.requiredDays} Days</p>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
