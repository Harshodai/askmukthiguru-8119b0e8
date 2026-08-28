import React from 'react';
import { motion } from 'framer-motion';
import { Play, Pause } from 'lucide-react';

interface SacredVoicePlayerProps {
  text?: string;
  isSpeaking: boolean;
  onTogglePlay: () => void;
  speed?: number;
  onChangeSpeed?: (speed: number) => void;
}

export const SacredVoicePlayer: React.FC<SacredVoicePlayerProps> = ({
  isSpeaking,
  onTogglePlay,
  speed = 1.0,
  onChangeSpeed,
}) => {
  const speeds = [0.8, 1.0, 1.2];

  return (
    <div className="mt-2 flex items-center justify-between rounded-xl border border-saffron-gold/20 bg-gradient-to-r from-saffron-gold/10 via-card to-card px-3 py-1.5 shadow-sm">
      <div className="flex items-center gap-2.5">
        <button
          type="button"
          onClick={onTogglePlay}
          className="flex h-7 w-7 items-center justify-center rounded-full bg-saffron-gold text-primary-foreground shadow-sm hover:bg-amber-500 transition-colors"
          aria-label={isSpeaking ? 'Pause Guru Voice' : 'Listen to Guru Voice'}
        >
          {isSpeaking ? <Pause className="h-3.5 w-3.5 fill-current" /> : <Play className="h-3.5 w-3.5 fill-current ml-0.5" />}
        </button>

        {/* Live Sacred Waveform Visualizer */}
        <div className="flex items-center gap-0.5">
          {[12, 20, 8, 16, 24, 14, 18, 10, 22, 12].map((height, idx) => (
            <motion.span
              key={idx}
              animate={isSpeaking ? { height: [height * 0.4, height, height * 0.3] } : { height: 4 }}
              transition={isSpeaking ? { duration: 0.6, repeat: Infinity, delay: idx * 0.06 } : { duration: 0.2 }}
              className="w-1 rounded-full bg-saffron-gold/70"
              style={{ minHeight: '4px' }}
            />
          ))}
        </div>

        <span className="font-serif text-xs text-saffron-gold font-medium">Guru Voice</span>
      </div>

      {onChangeSpeed && (
        <div className="flex items-center gap-1.5">
          {speeds.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onChangeSpeed(s)}
              className={`rounded-md px-1.5 py-0.5 font-mono text-[10px] font-medium transition-colors ${
                speed === s ? 'bg-saffron-gold text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {s}x
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
