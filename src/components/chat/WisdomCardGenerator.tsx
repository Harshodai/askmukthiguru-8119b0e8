import { useState, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Download, Share2, Sparkles, Check } from 'lucide-react';
import { toPng } from 'html-to-image';

interface WisdomCardGeneratorProps {
  isOpen: boolean;
  onClose: () => void;
  content: string;
}

const CARD_STYLES = [
  { id: 'golden', label: 'Golden Hour', bg: 'from-[#D4A574] via-[#C4956A] to-[#8B6914]', text: 'text-white' },
  { id: 'lotus', label: 'Lotus Night', bg: 'from-[#1a1a2e] via-[#16213e] to-[#0f3460]', text: 'text-white' },
  { id: 'dawn', label: 'Sacred Dawn', bg: 'from-[#ffecd2] via-[#fcb69f] to-[#ff9a9e]', text: 'text-[#3d2c2c]' },
] as const;

export const WisdomCardGenerator = ({ isOpen, onClose, content }: WisdomCardGeneratorProps) => {
  const [selectedStyle, setSelectedStyle] = useState(0);
  const [shared, setShared] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  const style = CARD_STYLES[selectedStyle];

  // Truncate to ~280 chars for card readability
  const truncated = content.length > 280 ? content.slice(0, 277) + '…' : content;

  const generateImage = useCallback(async (): Promise<Blob | null> => {
    if (!cardRef.current) return null;
    try {
      const dataUrl = await toPng(cardRef.current, { pixelRatio: 2, cacheBust: true });
      const res = await fetch(dataUrl);
      return await res.blob();
    } catch (err) {
      console.error('Failed to generate wisdom card image:', err);
      return null;
    }
  }, []);

  const handleDownload = useCallback(async () => {
    const blob = await generateImage();
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'wisdom-card.png';
    a.click();
    URL.revokeObjectURL(url);
  }, [generateImage]);

  const handleShare = useCallback(async () => {
    const blob = await generateImage();
    if (!blob) return;

    if (navigator.share) {
      try {
        const file = new File([blob], 'wisdom-card.png', { type: 'image/png' });
        await navigator.share({
          title: 'Wisdom from AskMukthiGuru',
          text: truncated,
          files: [file],
        });
        setShared(true);
        setTimeout(() => setShared(false), 2000);
        return;
      } catch {
        // User cancelled or not supported — fall through to download
      }
    }

    // Fallback: copy text
    try {
      await navigator.clipboard.writeText(`"${truncated}"\n\n— AskMukthiGuru`);
      setShared(true);
      setTimeout(() => setShared(false), 2000);
    } catch {
      handleDownload();
    }
  }, [generateImage, truncated, handleDownload]);

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md space-y-4"
          >
            {/* Style selector */}
            <div className="flex items-center justify-between">
              <div className="flex gap-2">
                {CARD_STYLES.map((s, i) => (
                  <button
                    key={s.id}
                    onClick={() => setSelectedStyle(i)}
                    className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all border ${
                      i === selectedStyle
                        ? 'border-ojas bg-ojas/10 text-ojas'
                        : 'border-border text-muted-foreground hover:border-ojas/40'
                    }`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
              <button onClick={onClose} className="p-1.5 rounded-full hover:bg-muted transition-colors">
                <X className="w-4 h-4 text-muted-foreground" />
              </button>
            </div>

            {/* Card preview */}
            <div
              ref={cardRef}
              className={`relative overflow-hidden rounded-2xl bg-gradient-to-br ${style.bg} p-8 shadow-2xl`}
              style={{ minHeight: 280 }}
            >
              {/* Lotus watermark */}
              <div className="absolute top-4 right-4 opacity-10">
                <Sparkles className="w-20 h-20" />
              </div>
              <div className="absolute bottom-4 left-4 opacity-10">
                <Sparkles className="w-12 h-12" />
              </div>

              <div className="relative z-10 flex flex-col justify-between h-full min-h-[200px]">
                <div>
                  <p className={`text-lg leading-relaxed font-serif italic ${style.text}`}>
                    "{truncated}"
                  </p>
                </div>
                <div className="mt-6 flex items-center gap-2">
                  <Sparkles className={`w-4 h-4 ${style.text} opacity-70`} />
                  <span className={`text-sm font-medium ${style.text} opacity-80`}>
                    AskMukthiGuru
                  </span>
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-2">
              <button
                onClick={handleDownload}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-card border border-border hover:border-ojas/40 transition-colors text-sm font-medium"
              >
                <Download className="w-4 h-4" />
                Download
              </button>
              <button
                onClick={handleShare}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity"
              >
                {shared ? <Check className="w-4 h-4" /> : <Share2 className="w-4 h-4" />}
                {shared ? 'Shared!' : 'Share'}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
