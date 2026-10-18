import { useState, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Download, Share2, Sparkles, Check } from 'lucide-react';
import { toPng } from 'html-to-image';
import { useTranslation } from 'react-i18next';

interface WisdomCardGeneratorProps {
  isOpen: boolean;
  onClose: () => void;
  content: string;
}

const CARD_STYLES = [
  {
    id: 'ekam',
    label: 'Ekam Sanctuary',
    image: '/og/og-teachings.jpg',
    overlay: 'from-black/85 via-black/55 to-black/75',
    text: 'text-amber-50',
    accent: 'text-amber-300',
    border: 'border-amber-400/30',
  },
  {
    id: 'serene',
    label: 'Serene Mind',
    image: '/og/og-serene.jpg',
    overlay: 'from-black/85 via-emerald-950/45 to-black/70',
    text: 'text-white',
    accent: 'text-emerald-300',
    border: 'border-emerald-400/30',
  },
  {
    id: 'dawn',
    label: 'Sacred Dawn',
    image: '/og/og-practices.jpg',
    overlay: 'from-black/85 via-rose-950/40 to-black/60',
    text: 'text-white',
    accent: 'text-rose-300',
    border: 'border-rose-400/30',
  },
  {
    id: 'night',
    label: 'Obsidian Night',
    image: '/og/og-guides.jpg',
    overlay: 'from-black/90 via-slate-950/70 to-black/80',
    text: 'text-white',
    accent: 'text-amber-400',
    border: 'border-amber-400/40',
  },
] as const;

export const WisdomCardGenerator = ({ isOpen, onClose, content }: WisdomCardGeneratorProps) => {
  const { t } = useTranslation();
  const [selectedStyle, setSelectedStyle] = useState(0);
  const [shared, setShared] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  const style = CARD_STYLES[selectedStyle];

  // Clean quote: strip markdown headers or leading blockquote markers for clean card rendering
  const cleanedContent = content
    .replace(/^###\s+.*$/gm, '')
    .replace(/^>\s*/gm, '')
    .replace(/^—\s*.*$/gm, '')
    .replace(/^Sources:.*$/gm, '')
    .trim();

  const displayContent = cleanedContent || content;
  // Truncate to ~280 chars for card readability
  const truncated = displayContent.length > 280 ? displayContent.slice(0, 277) + '…' : displayContent;

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
    setDownloading(true);
    try {
      const blob = await generateImage();
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `askmukthiguru-wisdom-${style.id}.png`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  }, [generateImage, style.id]);

  const handleShare = useCallback(async () => {
    const blob = await generateImage();
    if (!blob) return;

    if (navigator.share) {
      try {
        const file = new File([blob], `wisdom-${style.id}.png`, { type: 'image/png' });
        await navigator.share({
          title: 'Wisdom from AskMukthiGuru',
          text: `"${truncated}"\n\n— Sri Krishnaji & Sri Preethaji`,
          files: [file],
        });
        setShared(true);
        setTimeout(() => setShared(false), 2000);
        return;
      } catch {
        // User cancelled or share failed — fall back to download or copy
      }
    }

    // Fallback: copy text to clipboard
    try {
      await navigator.clipboard.writeText(`"${truncated}"\n\n— AskMukthiGuru`);
      setShared(true);
      setTimeout(() => setShared(false), 2000);
    } catch {
      handleDownload();
    }
  }, [generateImage, truncated, handleDownload, style.id]);

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-background/85 backdrop-blur-md p-4 safe-x"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.94, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.94, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-lg space-y-4"
          >
            {/* Theme selector bar with photo preview pills */}
            <div className="flex items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-1.5 max-w-[85%]">
                {CARD_STYLES.map((s, i) => (
                  <button
                    key={s.id}
                    onClick={() => setSelectedStyle(i)}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all border ${
                      i === selectedStyle
                        ? 'border-ojas bg-ojas/15 text-ojas shadow-sm'
                        : 'border-border/70 text-muted-foreground hover:border-ojas/40 hover:text-foreground'
                    }`}
                  >
                    <img
                      src={s.image}
                      alt=""
                      className="w-3.5 h-3.5 rounded-full object-cover shrink-0 ring-1 ring-white/20"
                    />
                    <span>{s.label}</span>
                  </button>
                ))}
              </div>
              <button
                onClick={onClose}
                aria-label={t('common.close', 'Close')}
                className="p-1.5 rounded-full hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Card preview container */}
            <div
              ref={cardRef}
              className={`relative overflow-hidden rounded-2xl p-7 sm:p-9 shadow-2xl flex flex-col justify-between border ${style.border}`}
              style={{ minHeight: 320 }}
            >
              {/* Photo background */}
              <img
                src={style.image}
                alt=""
                crossOrigin="anonymous"
                className="absolute inset-0 w-full h-full object-cover pointer-events-none select-none"
              />

              {/* Multi-stop gradient vignette overlay for typography legibility */}
              <div
                className={`absolute inset-0 bg-gradient-to-br ${style.overlay} backdrop-blur-[0.5px] pointer-events-none`}
              />

              {/* Sacred subtle watermark */}
              <div className="absolute top-4 right-4 opacity-15 pointer-events-none text-white">
                <Sparkles className="w-16 h-16" />
              </div>
              <div className="absolute bottom-4 left-4 opacity-10 pointer-events-none text-white">
                <Sparkles className="w-10 h-10" />
              </div>

              {/* Quote & Brand Content */}
              <div className="relative z-10 flex flex-col justify-between h-full min-h-[220px]">
                <div>
                  <p className={`text-lg sm:text-xl font-serif leading-relaxed italic ${style.text} drop-shadow-md`}>
                    &ldquo;{truncated}&rdquo;
                  </p>
                </div>
                <div className="mt-8 flex items-center justify-between border-t border-white/15 pt-3">
                  <div className="flex items-center gap-2">
                    <Sparkles className={`w-4 h-4 ${style.accent}`} />
                    <span className={`text-xs font-semibold uppercase tracking-[0.18em] ${style.accent}`}>
                      AskMukthiGuru
                    </span>
                  </div>
                  <span className="text-[11px] text-white/70 tracking-wider">
                    Sri Krishnaji & Sri Preethaji
                  </span>
                </div>
              </div>
            </div>

            {/* Export & Share Action Buttons */}
            <div className="flex gap-2.5">
              <button
                type="button"
                onClick={handleDownload}
                disabled={downloading}
                className="flex-1 min-h-[44px] flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-card border border-border/80 hover:border-ojas/40 hover:bg-muted/40 transition-colors text-sm font-medium text-foreground"
              >
                <Download className="w-4 h-4 text-ojas" />
                {downloading ? t('common.downloading', 'Saving…') : t('common.downloadPng', 'Download PNG')}
              </button>
              <button
                type="button"
                onClick={handleShare}
                className="flex-1 min-h-[44px] flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity shadow-sm"
              >
                {shared ? <Check className="w-4 h-4" /> : <Share2 className="w-4 h-4" />}
                {shared ? t('common.shared', 'Shared!') : t('common.share', 'Share Wisdom')}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
