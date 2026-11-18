import React from 'react';
import { motion } from 'framer-motion';
import { Flame, Award, Sparkles, Shield, Compass, Heart, Lock } from 'lucide-react';
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
  currentStreak?: number;
  longestStreak?: number;
  nextMilestoneDays?: number;
}

export const SACRED_MILESTONES: Omit<MilestoneBadge, 'unlocked'>[] = [
  {
    id: 'awakening_spark',
    name: '3-Day Practice',
    sanskritName: 'Prarambha',
    requiredDays: 3,
    description: 'Completed 3 consecutive days of recorded practice.',
    icon: Sparkles,
  },
  {
    id: 'serene_mind_master',
    name: '7-Day Practice',
    sanskritName: 'Shanta Manas',
    requiredDays: 7,
    description: 'Completed 7 consecutive days of recorded practice.',
    icon: Flame,
  },
  {
    id: 'witnessing_presence',
    name: '14-Day Practice',
    sanskritName: 'Sakshi Bhava',
    requiredDays: 14,
    description: 'Reached 14 consecutive days of recorded practice.',
    icon: Compass,
  },
  {
    id: 'deeksha_sadhak',
    name: '21-Day Practice',
    sanskritName: 'Deeksha Sadhana',
    requiredDays: 21,
    description: 'Reached 21 consecutive days of recorded practice.',
    icon: Heart,
  },
  {
    id: 'transformation_tapasya',
    name: '40-Day Practice',
    sanskritName: 'Tapasya Siddhi',
    requiredDays: 40,
    description: 'Reached 40 consecutive days of recorded practice.',
    icon: Shield,
  },
  {
    id: 'mukthi_luminary',
    name: '108-Day Practice',
    sanskritName: 'Mukthi Jnani',
    requiredDays: 108,
    description: 'Reached 108 consecutive days of recorded practice.',
    icon: Award,
  },
];

export const StreakMilestoneCard: React.FC<StreakMilestoneCardProps> = ({
  currentStreak = 0,
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

  const unlockedCount = milestones.filter((m) => m.unlocked).length;

  return (
    <div className="rounded-2xl border border-saffron-gold/30 bg-gradient-to-br from-card via-card to-saffron-gold/5 p-5 sm:p-6 shadow-xs space-y-4">
      {/* Header with Title and Integrated Next Milestone Progress */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-saffron-gold/15 border border-saffron-gold/30 flex items-center justify-center text-saffron-gold shrink-0">
              <Award className="w-4 h-4" aria-hidden="true" />
            </div>
            <div>
              <h4 className="text-sm font-semibold text-foreground tracking-tight flex items-center gap-2">
                <span>Practice Milestones & Sacred Badges</span>
                <span className="text-[11px] font-mono font-medium text-saffron-gold px-2 py-0.5 rounded-full bg-saffron-gold/10 border border-saffron-gold/20">
                  {unlockedCount} / {milestones.length} Unlocked
                </span>
              </h4>
            </div>
          </div>
        </div>

        {/* Milestone Progress Mini-Bar */}
        <div className="w-full sm:w-64 space-y-1.5 rounded-xl bg-background/60 border border-border/40 p-2.5">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground font-medium truncate">
              {nextMilestone.unlocked ? 'All Milestones Reached' : `Next: ${nextMilestone.name}`}
            </span>
            <span className="font-mono text-saffron-gold font-semibold shrink-0 ml-2">
              {currentStreak}/{nextMilestone.requiredDays}d
            </span>
          </div>
          <Progress value={progressPercent} className="h-1.5 bg-muted/60" />
        </div>
      </div>

      {/* 6 Sacred Milestone Badges Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2.5 sm:gap-3">
        {milestones.map((m) => {
          const Icon = m.icon;
          return (
            <motion.div
              key={m.id}
              whileHover={{ y: -2, scale: 1.02 }}
              className={`relative group rounded-2xl border p-3.5 flex flex-col items-center text-center space-y-2 transition-all ${
                m.unlocked
                  ? 'bg-gradient-to-b from-saffron-gold/15 to-card border-saffron-gold/40 shadow-xs'
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
                <p className="text-xs font-semibold font-sans text-foreground truncate">{m.name}</p>
                <p className="text-[10px] font-mono text-saffron-gold/80 italic">{m.sanskritName}</p>
                <p className="text-[10px] text-muted-foreground">{m.requiredDays} Days</p>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
};
