import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ChevronLeft, ChevronRight, MessageSquare, Brain, Flame, Sparkles } from 'lucide-react';

const TOUR_KEY = 'askmukthiguru_tour_seen';

export const hasSeenTour = () => {
  try { return localStorage.getItem(TOUR_KEY) === '1'; } catch { return true; }
};

export const markTourSeen = () => {
  try { localStorage.setItem(TOUR_KEY, '1'); } catch {}
};

interface DemoModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const SLIDES = [
  {
    id: 'chat',
    icon: MessageSquare,
    emoji: '💬',
    title: 'Talk to Your Guru',
    subtitle: 'Ask anything — stress, purpose, relationships — get thoughtful guidance.',
    color: '#d4af37',
    glow: 'rgba(212, 175, 55, 0.25)',
    preview: (
      <div className="space-y-3 px-1 flex flex-col justify-center" style={{ height: 160 }}>
        <motion.div
          initial={{ opacity: 0, x: 16 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.15 }}
          className="flex gap-2 items-end justify-end"
        >
          <div
            style={{
              background: 'rgba(255,255,255,0.06)',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '14px 14px 4px 14px',
              padding: '8px 12px',
              fontSize: 12.5,
              color: 'rgba(255,255,255,0.85)',
              maxWidth: 240,
              lineHeight: 1.45,
            }}
          >
            Namaste. My mind won't stop racing.
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: -16 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.55 }}
          className="flex gap-2 items-end"
        >
          <div
            style={{
              width: 26, height: 26, borderRadius: '50%',
              background: 'linear-gradient(135deg,#d4af37,#f59e0b)',
              flexShrink: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 11,
              boxShadow: '0 2px 6px rgba(212, 175, 55, 0.4)',
            }}
          >
            🙏
          </div>
          <div
            style={{
              background: 'rgba(212, 175, 55, 0.12)',
              border: '1px solid rgba(212, 175, 55, 0.25)',
              borderRadius: '14px 14px 14px 4px',
              padding: '8px 12px',
              fontSize: 12.5,
              color: 'rgba(255,255,255,0.95)',
              maxWidth: 260,
              lineHeight: 1.45,
              boxShadow: '0 0 15px rgba(212, 175, 55, 0.05)',
            }}
          >
            Try this: sit for 2 minutes, watch thoughts like clouds passing. Don't fight — just notice. The racing slows naturally.
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: 16 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.95 }}
          className="flex gap-2 items-end justify-end"
        >
          <div
            style={{
              background: 'rgba(255,255,255,0.06)',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '14px 14px 4px 14px',
              padding: '8px 12px',
              fontSize: 12.5,
              color: 'rgba(255,255,255,0.85)',
              maxWidth: 240,
              lineHeight: 1.45,
            }}
          >
            That simple? I can do that daily.
          </div>
        </motion.div>
      </div>
    ),
  },
  {
    id: 'meditation',
    icon: Flame,
    emoji: '🧘',
    title: '3-Minute Calm',
    subtitle: 'Quick breathing practice — before meetings, bedtime, or whenever you need center.',
    color: '#d4af37',
    glow: 'rgba(212, 175, 55, 0.25)',
    preview: (
      <div className="flex flex-col items-center justify-center space-y-3" style={{ height: 160 }}>
        <motion.div
          animate={{ scale: [1, 1.22, 1], opacity: [0.7, 1, 0.7] }}
          transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
          style={{
            width: 72, height: 72, borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(212,175,55,0.6) 0%, rgba(212,175,55,0.2) 60%, transparent 100%)',
            border: '2px solid rgba(212,175,55,0.4)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 0 40px rgba(212,175,55,0.3)',
          }}
        >
          <motion.div
            animate={{ scale: [1, 0.85, 1] }}
            transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
            style={{ width: 44, height: 44, borderRadius: '50%', background: 'rgba(212,175,55,0.3)', border: '1px solid rgba(212,175,55,0.5)' }}
          />
        </motion.div>
        <motion.p
          animate={{ opacity: [0.5, 1, 0.5] }}
          transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
          style={{ fontSize: 13, color: 'rgba(212,175,55,0.9)', letterSpacing: '0.08em', textTransform: 'uppercase', fontWeight: 600 }}
        >
          Breathe in...
        </motion.p>
        <div style={{ width: 200, height: 3, background: 'rgba(255,255,255,0.08)', borderRadius: 100, overflow: 'hidden' }}>
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: '60%' }}
            transition={{ duration: 1.5, delay: 0.4 }}
            style={{ height: '100%', background: 'linear-gradient(90deg,#d4af37,#fbbf24)', borderRadius: 100 }}
          />
        </div>
        <p style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>1:48 remaining</p>
      </div>
    ),
  },
  {
    id: 'knowledge',
    icon: Brain,
    emoji: '🕸️',
    title: 'Your Wisdom Map',
    subtitle: 'Every chat builds a living web — see how insights connect over time.',
    color: '#d4af37',
    glow: 'rgba(212, 175, 55, 0.25)',
    preview: (
      <div className="relative" style={{ height: 150, width: '100%' }}>
        <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', zIndex: 0 }}>
          <line x1="50%" y1="38%" x2="18%" y2="20%" stroke="#d4af37" strokeWidth="1" strokeOpacity="0.35" />
          <line x1="50%" y1="38%" x2="82%" y2="20%" stroke="#d4af37" strokeWidth="1" strokeOpacity="0.35" />
          <line x1="50%" y1="38%" x2="12%" y2="70%" stroke="#d4af37" strokeWidth="1" strokeOpacity="0.35" />
          <line x1="50%" y1="38%" x2="88%" y2="70%" stroke="#d4af37" strokeWidth="1" strokeOpacity="0.35" />
          <line x1="50%" y1="38%" x2="50%" y2="88%" stroke="#d4af37" strokeWidth="1" strokeOpacity="0.35" />
          <line x1="18%" y1="20%" x2="12%" y2="70%" stroke="#d4af37" strokeWidth="1" strokeOpacity="0.2" />
          <line x1="82%" y1="20%" x2="88%" y2="70%" stroke="#d4af37" strokeWidth="1" strokeOpacity="0.2" />
        </svg>

        {[
          { x: 50, y: 38, label: 'Peace', size: 28, color: '#d4af37', main: true },
          { x: 18, y: 20, label: 'Breath', size: 18, color: '#fbbf24' },
          { x: 82, y: 20, label: 'Gratitude', size: 20, color: '#fbbf24' },
          { x: 12, y: 70, label: 'Stillness', size: 16, color: '#fde68a' },
          { x: 88, y: 70, label: 'Kindness', size: 18, color: '#fde68a' },
          { x: 50, y: 88, label: 'Letting Go', size: 16, color: '#fde68a' },
        ].map((node, i) => (
          <div key={i} style={{ position: 'absolute', left: `${node.x}%`, top: `${node.y}%`, transform: 'translate(-50%, -50%)', textAlign: 'center', zIndex: 1 }}>
            <div
              style={{
                width: node.size, height: node.size, borderRadius: '50%',
                background: `radial-gradient(circle, ${node.color}50, ${node.color}20)`,
                border: `1.5px solid ${node.color}70`,
                boxShadow: `0 0 14px ${node.color}30`,
                margin: '0 auto',
              }}
            >
              {node.main && (
                <motion.div
                  animate={{ scale: [1, 1.4, 1] }}
                  transition={{ duration: 2.5, repeat: Infinity }}
                  style={{ width: 6, height: 6, borderRadius: '50%', background: node.color, margin: '0 auto', position: 'relative', top: '50%', transform: 'translateY(-50%)' }}
                />
              )}
            </div>
            <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.55)', fontWeight: 500, whiteSpace: 'nowrap', marginTop: 3, display: 'block' }}>
              {node.label}
            </span>
          </div>
        ))}
      </div>
    ),
  },
];

export const DemoModal = ({ isOpen, onClose }: DemoModalProps) => {
  const [slide, setSlide] = useState(0);
  const current = SLIDES[slide];
  const Icon = current.icon;

  useEffect(() => {
    if (isOpen) {
      markTourSeen();
      setSlide(0);
    }
  }, [isOpen]);

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
            initial={{ opacity: 0, scale: 0.92 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.94 }}
            transition={{ type: 'spring', stiffness: 340, damping: 28 }}
            style={{
              position: 'fixed',
              top: '50%',
              left: '50%',
              marginLeft: '-280px',
              marginTop: '-240px',
              zIndex: 9991,
              width: 560,
              maxHeight: '85vh',
              overflowY: 'auto',
            }}
          >
            {/* Outer shell */}
            <div
              style={{
                width: '100%',
                background: 'rgba(24, 18, 15, 0.95)',
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
                  background: 'linear-gradient(145deg, rgba(32, 25, 20, 0.98) 0%, rgba(20, 16, 13, 0.99) 100%)',
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
                      Step {slide + 1} of {SLIDES.length}
                    </p>
                    <p style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>Quick Tour</p>
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
                      {/* Preview area */}
                      <div
                        style={{
                          background: 'rgba(255,255,255,0.03)',
                          border: `1px solid ${current.color}18`,
                          borderRadius: 16,
                          padding: '16px',
                          minHeight: 200,
                          overflow: 'hidden',
                        }}
                      >
                        {/* Emoji + Title + Subtitle inside preview */}
                        <div style={{ marginBottom: 12 }}>
                          <span style={{ fontSize: 28, filter: `drop-shadow(0 4px 12px ${current.color}50)` }}>
                            {current.emoji}
                          </span>
                          <h2
                            style={{
                              fontSize: 20,
                              fontWeight: 800,
                              color: '#fff',
                              letterSpacing: '-0.03em',
                              lineHeight: 1.2,
                              marginTop: 6,
                              marginBottom: 4,
                            }}
                          >
                            {current.title}
                          </h2>
                          <p style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.5)', lineHeight: 1.5, overflowWrap: 'break-word', wordBreak: 'break-word' }}>
                            {current.subtitle}
                          </p>
                        </div>
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
                      href="/chat"
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
                      Start Chatting
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
