import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ChevronLeft, ChevronRight, MessageSquare, Brain, Flame, Sparkles } from 'lucide-react';

interface DemoModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const SLIDES = [
  {
    id: 'chat',
    icon: MessageSquare,
    emoji: '✨',
    title: 'Ask Anything. Receive Wisdom.',
    subtitle: 'AI-guided spiritual conversations rooted in the teachings of Sri Preethaji & Sri Krishnaji.',
    color: '#d4af37',
    glow: 'rgba(212, 175, 55, 0.25)',
    preview: (
      <div className="space-y-3 px-1">
        {/* Simulated chat bubbles */}
        <motion.div
          initial={{ opacity: 0, x: -16 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.15 }}
          className="flex gap-2 items-end"
        >
          <div
            style={{
              width: 28, height: 28, borderRadius: '50%',
              background: 'linear-gradient(135deg,#d4af37,#f59e0b)',
              flexShrink: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 12,
            }}
          >
            💫
          </div>
          <div
            style={{
              background: 'rgba(212, 175, 55, 0.12)',
              border: '1px solid rgba(212, 175, 55, 0.25)',
              borderRadius: '16px 16px 16px 4px',
              padding: '10px 14px',
              fontSize: 13,
              color: 'rgba(255,255,255,0.9)',
              maxWidth: 260,
              lineHeight: 1.5,
            }}
          >
            How can I find peace when my mind won't stop?
          </div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, x: 16 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.45 }}
          className="flex gap-2 items-end justify-end"
        >
          <div
            style={{
              background: 'rgba(255,255,255,0.06)',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '16px 16px 4px 16px',
              padding: '10px 14px',
              fontSize: 13,
              color: 'rgba(255,255,255,0.75)',
              maxWidth: 280,
              lineHeight: 1.6,
            }}
          >
            The Beautiful State isn't something you achieve — it's what remains when suffering dissolves. Begin by observing your thoughts without becoming them...
          </div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, x: -16 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.75 }}
          className="flex gap-2 items-end"
        >
          <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'linear-gradient(135deg,#d4af37,#f59e0b)', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12 }}>💫</div>
          <div style={{ background: 'rgba(212, 175, 55, 0.12)', border: '1px solid rgba(212, 175, 55, 0.25)', borderRadius: '16px 16px 16px 4px', padding: '10px 14px', fontSize: 13, color: 'rgba(255,255,255,0.9)', maxWidth: 240, lineHeight: 1.5 }}>
            What does "observing without becoming" mean?
          </div>
        </motion.div>
      </div>
    ),
  },
  {
    id: 'meditation',
    icon: Flame,
    emoji: '🧘',
    title: 'Serene Mind Meditation',
    subtitle: '3-minute guided breathwork to calm the mind and enter the Beautiful State — available any time.',
    color: '#a78bfa',
    glow: 'rgba(167, 139, 250, 0.25)',
    preview: (
      <div className="flex flex-col items-center justify-center py-4 gap-5">
        {/* Breathing orb */}
        <motion.div
          animate={{ scale: [1, 1.22, 1], opacity: [0.7, 1, 0.7] }}
          transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
          style={{
            width: 88, height: 88, borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(167,139,250,0.6) 0%, rgba(139,92,246,0.2) 60%, transparent 100%)',
            border: '2px solid rgba(167,139,250,0.4)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 0 40px rgba(167,139,250,0.3)',
          }}
        >
          <motion.div
            animate={{ scale: [1, 0.85, 1] }}
            transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
            style={{ width: 56, height: 56, borderRadius: '50%', background: 'rgba(167,139,250,0.3)', border: '1px solid rgba(167,139,250,0.5)' }}
          />
        </motion.div>
        <motion.p
          animate={{ opacity: [0.5, 1, 0.5] }}
          transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
          style={{ fontSize: 13, color: 'rgba(167,139,250,0.9)', letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 600 }}
        >
          Breathe in...
        </motion.p>
        {/* Timer bar */}
        <div style={{ width: 200, height: 3, background: 'rgba(255,255,255,0.08)', borderRadius: 100, overflow: 'hidden' }}>
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: '60%' }}
            transition={{ duration: 1.5, delay: 0.4 }}
            style={{ height: '100%', background: 'linear-gradient(90deg,#a78bfa,#c4b5fd)', borderRadius: 100 }}
          />
        </div>
        <p style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>1:48 remaining</p>
      </div>
    ),
  },
  {
    id: 'knowledge',
    icon: Brain,
    emoji: '🧠',
    title: 'Your Wisdom Knowledge Graph',
    subtitle: 'Watch your insights form a living map of concepts, teachings, and personal breakthroughs.',
    color: '#34d399',
    glow: 'rgba(52, 211, 153, 0.25)',
    preview: (
      <div className="relative flex items-center justify-center" style={{ height: 160 }}>
        {/* Nodes */}
        {[
          { x: 50, y: 50, label: 'Beautiful State', size: 28, color: '#34d399', delay: 0.1 },
          { x: 20, y: 25, label: 'Equanimity', size: 20, color: '#6ee7b7', delay: 0.25 },
          { x: 78, y: 30, label: 'Awareness', size: 22, color: '#6ee7b7', delay: 0.35 },
          { x: 15, y: 70, label: 'Presence', size: 18, color: '#a7f3d0', delay: 0.45 },
          { x: 80, y: 72, label: 'Compassion', size: 20, color: '#a7f3d0', delay: 0.55 },
          { x: 50, y: 85, label: 'Surrender', size: 17, color: '#a7f3d0', delay: 0.65 },
        ].map((node, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, scale: 0 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: node.delay, type: 'spring', stiffness: 300 }}
            style={{
              position: 'absolute',
              left: `${node.x}%`,
              top: `${node.y}%`,
              transform: 'translate(-50%,-50%)',
              width: node.size,
              height: node.size,
              borderRadius: '50%',
              background: `radial-gradient(circle, ${node.color}40, ${node.color}15)`,
              border: `1px solid ${node.color}60`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: `0 0 12px ${node.color}30`,
            }}
          >
            {i === 0 && (
              <motion.div
                animate={{ scale: [1, 1.3, 1] }}
                transition={{ duration: 2.5, repeat: Infinity }}
                style={{ width: 6, height: 6, borderRadius: '50%', background: node.color }}
              />
            )}
          </motion.div>
        ))}
        {/* Connection lines */}
        <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', opacity: 0.3 }}>
          {[
            [50, 50, 20, 25], [50, 50, 78, 30], [50, 50, 15, 70],
            [50, 50, 80, 72], [50, 50, 50, 85],
          ].map(([x1, y1, x2, y2], i) => (
            <motion.line
              key={i}
              x1={`${x1}%`} y1={`${y1}%`}
              x2={`${x2}%`} y2={`${y2}%`}
              stroke="#34d399"
              strokeWidth={1}
              initial={{ pathLength: 0, opacity: 0 }}
              animate={{ pathLength: 1, opacity: 0.6 }}
              transition={{ delay: 0.3 + i * 0.1, duration: 0.5 }}
            />
          ))}
        </svg>
      </div>
    ),
  },
];

export const DemoModal = ({ isOpen, onClose }: DemoModalProps) => {
  const [slide, setSlide] = useState(0);
  const current = SLIDES[slide];
  const Icon = current.icon;

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            onClick={onClose}
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(0,0,0,0.80)',
              backdropFilter: 'blur(16px)',
              WebkitBackdropFilter: 'blur(16px)',
              zIndex: 9990,
            }}
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.92, y: 24 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.94, y: 12 }}
            transition={{ type: 'spring', stiffness: 340, damping: 28 }}
            style={{
              position: 'fixed',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              zIndex: 9991,
              width: '90vw',
              maxWidth: 560,
            }}
          >
            {/* Outer shell */}
            <div
              style={{
                background: 'rgba(8, 8, 12, 0.95)',
                border: `1px solid ${current.color}30`,
                borderRadius: 28,
                boxShadow: [
                  `0 0 0 1px ${current.color}12 inset`,
                  `0 32px 64px rgba(0,0,0,0.7)`,
                  `0 0 80px ${current.glow}`,
                ].join(', '),
                padding: 2,
                transition: 'box-shadow 0.4s ease, border-color 0.4s ease',
              }}
            >
              {/* Inner core */}
              <div
                style={{
                  borderRadius: 26,
                  background: 'linear-gradient(145deg, rgba(16,16,22,0.97) 0%, rgba(10,10,16,0.99) 100%)',
                  boxShadow: 'inset 0 1px 1px rgba(255,255,255,0.05)',
                  overflow: 'hidden',
                }}
              >
                {/* Header */}
                <div style={{ padding: '20px 24px 0', display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div
                    style={{
                      width: 36, height: 36, borderRadius: 10,
                      background: `${current.color}18`,
                      border: `1px solid ${current.color}30`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}
                  >
                    <Icon style={{ width: 16, height: 16, color: current.color }} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <p style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.15em', color: current.color, fontWeight: 700, marginBottom: 2 }}>
                      Feature {slide + 1} of {SLIDES.length}
                    </p>
                    <p style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>AskMukthiGuru Demo</p>
                  </div>
                  <button
                    onClick={onClose}
                    style={{
                      width: 32, height: 32, borderRadius: '50%',
                      background: 'rgba(255,255,255,0.05)',
                      border: '1px solid rgba(255,255,255,0.08)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      cursor: 'pointer', color: 'rgba(255,255,255,0.4)',
                    }}
                  >
                    <X style={{ width: 14, height: 14 }} />
                  </button>
                </div>

                {/* Slide content */}
                <div style={{ padding: '20px 24px' }}>
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={slide}
                      initial={{ opacity: 0, x: 24 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -24 }}
                      transition={{ duration: 0.22, ease: [0.32, 0.72, 0, 1] }}
                    >
                      {/* Emoji + Title */}
                      <div style={{ marginBottom: 8 }}>
                        <span style={{ fontSize: 32, filter: `drop-shadow(0 4px 12px ${current.color}50)` }}>
                          {current.emoji}
                        </span>
                        <h2
                          style={{
                            fontSize: 22,
                            fontWeight: 800,
                            color: '#fff',
                            letterSpacing: '-0.03em',
                            lineHeight: 1.2,
                            marginTop: 8,
                            marginBottom: 8,
                          }}
                        >
                          {current.title}
                        </h2>
                        <p style={{ fontSize: 14, color: 'rgba(255,255,255,0.5)', lineHeight: 1.6 }}>
                          {current.subtitle}
                        </p>
                      </div>

                      {/* Preview area */}
                      <div
                        style={{
                          background: 'rgba(255,255,255,0.03)',
                          border: `1px solid ${current.color}18`,
                          borderRadius: 16,
                          padding: '16px',
                          marginTop: 16,
                          minHeight: 160,
                        }}
                      >
                        {current.preview}
                      </div>
                    </motion.div>
                  </AnimatePresence>
                </div>

                {/* Footer navigation */}
                <div
                  style={{
                    padding: '0 24px 20px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                  }}
                >
                  {/* Slide dots */}
                  <div style={{ display: 'flex', gap: 6 }}>
                    {SLIDES.map((s, i) => (
                      <button
                        key={i}
                        onClick={() => setSlide(i)}
                        style={{
                          width: i === slide ? 20 : 6,
                          height: 6,
                          borderRadius: 100,
                          background: i === slide ? current.color : 'rgba(255,255,255,0.15)',
                          border: 'none',
                          padding: 0,
                          cursor: 'pointer',
                          transition: 'all 0.3s cubic-bezier(0.32,0.72,0,1)',
                        }}
                      />
                    ))}
                  </div>

                  <div style={{ flex: 1 }} />

                  {/* Prev */}
                  <button
                    onClick={() => setSlide(s => Math.max(0, s - 1))}
                    disabled={slide === 0}
                    style={{
                      width: 36, height: 36, borderRadius: '50%',
                      background: 'rgba(255,255,255,0.06)',
                      border: '1px solid rgba(255,255,255,0.1)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      cursor: slide === 0 ? 'default' : 'pointer',
                      opacity: slide === 0 ? 0.3 : 1,
                      color: '#fff',
                    }}
                  >
                    <ChevronLeft style={{ width: 16, height: 16 }} />
                  </button>

                  {/* Next / CTA */}
                  {slide < SLIDES.length - 1 ? (
                    <motion.button
                      onClick={() => setSlide(s => s + 1)}
                      whileHover={{ scale: 1.04 }}
                      whileTap={{ scale: 0.97 }}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        padding: '8px 18px',
                        borderRadius: 100,
                        background: `linear-gradient(135deg, ${current.color}, ${current.color}cc)`,
                        border: 'none',
                        color: '#fff',
                        fontSize: 13,
                        fontWeight: 700,
                        cursor: 'pointer',
                        boxShadow: `0 4px 16px ${current.glow}`,
                      }}
                    >
                      Next
                      <ChevronRight style={{ width: 14, height: 14 }} />
                    </motion.button>
                  ) : (
                    <motion.a
                      href="/auth"
                      whileHover={{ scale: 1.04 }}
                      whileTap={{ scale: 0.97 }}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        padding: '8px 18px',
                        borderRadius: 100,
                        background: 'linear-gradient(135deg, #d4af37, #f59e0b)',
                        color: '#fff',
                        fontSize: 13,
                        fontWeight: 700,
                        textDecoration: 'none',
                        boxShadow: '0 4px 20px rgba(212, 175, 55, 0.4)',
                      }}
                    >
                      <Sparkles style={{ width: 14, height: 14 }} />
                      Start Free
                    </motion.a>
                  )}
                </div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};
