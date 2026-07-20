/**
 * CachePage — Admin Cache Management
 *
 * Displays real-time stats for all three cache tiers (hot / exact / semantic)
 * and exposes an admin-only "Invalidate All Caches" action backed by
 * POST /admin/clear-cache.
 *
 * Design: Ethereal Glass × Asymmetric Bento (high-end-visual-design skill)
 */
import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Zap, Database, Network, Trash2, RefreshCw, CheckCircle2, AlertTriangle, X } from 'lucide-react';
import { getCacheMetrics, clearCache } from '@/admin/lib/api';
import type { CacheMetrics } from '@/admin/types';

// ─── Easing ────────────────────────────────────────────────────────────────
const SPRING = { type: 'spring', damping: 22, stiffness: 260 } as const;
const EASE_OUT: [number, number, number, number] = [0.32, 0.72, 0, 1];

// ─── Tier config ───────────────────────────────────────────────────────────
const TIERS = [
  {
    key: 'hot' as const,
    label: 'Hot Cache',
    sub: 'In-process LRU · ~0 ms',
    icon: Zap,
    glow: 'rgba(251,191,36,0.18)',
    ring: '#F59E0B',
    ringBg: 'rgba(245,158,11,0.08)',
    dot: 'bg-amber-400',
    textAccent: 'text-amber-400',
    borderAccent: 'border-amber-400/20',
  },
  {
    key: 'exact' as const,
    label: 'Exact Cache',
    sub: 'Redis key-value · ~1–5 ms',
    icon: Database,
    glow: 'rgba(99,102,241,0.18)',
    ring: '#818CF8',
    ringBg: 'rgba(129,140,248,0.08)',
    dot: 'bg-indigo-400',
    textAccent: 'text-indigo-400',
    borderAccent: 'border-indigo-400/20',
  },
  {
    key: 'semantic' as const,
    label: 'Semantic Cache',
    sub: 'Qdrant vector search · ~20–50 ms',
    icon: Network,
    glow: 'rgba(16,185,129,0.18)',
    ring: '#34D399',
    ringBg: 'rgba(52,211,153,0.08)',
    dot: 'bg-emerald-400',
    textAccent: 'text-emerald-400',
    borderAccent: 'border-emerald-400/20',
  },
] as const;

// ─── Animated ring progress ────────────────────────────────────────────────
function RingProgress({ pct, color, size = 72 }: { pct: number; color: string; size?: number }) {
  const r = (size - 8) / 2;
  const circ = 2 * Math.PI * r;
  const dash = circ * (1 - pct / 100);
  return (
    <svg width={size} height={size} className="rotate-[-90deg]">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth={5} />
      <motion.circle
        cx={size / 2} cy={size / 2} r={r}
        fill="none"
        stroke={color}
        strokeWidth={5}
        strokeLinecap="round"
        strokeDasharray={circ}
        initial={{ strokeDashoffset: circ }}
        animate={{ strokeDashoffset: dash }}
        transition={{ duration: 1.1, ease: EASE_OUT }}
      />
    </svg>
  );
}

// ─── Individual tier card ──────────────────────────────────────────────────
function TierCard({
  tier,
  stats,
  result,
  idx,
}: {
  tier: typeof TIERS[number];
  stats: Record<string, unknown> | undefined;
  result: string | undefined;
  idx: number;
}) {
  const Icon = tier.icon;
  const available = stats?.available !== false;
  const size: number | null = typeof stats?.size === 'number' ? stats.size : null;
  const hits: number | null = typeof stats?.hits === 'number' ? stats.hits : null;
  const misses: number | null = typeof stats?.misses === 'number' ? stats.misses : null;
  const hitRate = hits != null && misses != null && hits + misses > 0
    ? Math.round((hits / (hits + misses)) * 100) : null;

  const cleared = result === 'cleared';
  const errored = result?.startsWith('error');

  return (
    <motion.div
      initial={{ opacity: 0, y: 28, filter: 'blur(6px)' }}
      animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
      transition={{ delay: idx * 0.09, duration: 0.65, ease: EASE_OUT }}
      className="relative group"
    >
      {/* Outer shell — Double-Bezel */}
      <div
        className={`p-[1.5px] rounded-[1.6rem] ring-1 ${tier.borderAccent} bg-white/[0.02] transition-all duration-700 ease-[cubic-bezier(0.32,0.72,0,1)] group-hover:ring-white/10`}
        style={{ boxShadow: `0 0 40px ${tier.glow}` }}
      >
        {/* Inner core */}
        <div
          className="rounded-[calc(1.6rem-1.5px)] px-6 py-6 flex flex-col gap-5"
          style={{ background: 'rgba(10,10,14,0.85)', backdropFilter: 'blur(24px)' }}
        >
          {/* Header row */}
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              {/* Icon island */}
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
                style={{ background: tier.ringBg, boxShadow: `inset 0 1px 1px rgba(255,255,255,0.1)` }}
              >
                <Icon className={`w-4.5 h-4.5 ${tier.textAccent}`} strokeWidth={1.5} />
              </div>
              <div>
                <p className="text-[13px] font-semibold text-white/90 leading-tight">{tier.label}</p>
                <p className="text-[10px] text-white/35 mt-0.5">{tier.sub}</p>
              </div>
            </div>

            {/* Status pill */}
            <div className={`shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-medium ${available ? `${tier.textAccent} bg-white/5` : 'text-white/30 bg-white/5'}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${available ? tier.dot : 'bg-white/20'}`} />
              {available ? 'Online' : 'Offline'}
            </div>
          </div>

          {/* Ring + metrics row */}
          <div className="flex items-center gap-5">
            {hitRate != null ? (
              <div className="relative shrink-0">
                <RingProgress pct={hitRate} color={tier.ring} />
                <span className={`absolute inset-0 flex items-center justify-center text-[13px] font-bold rotate-90 ${tier.textAccent}`}>
                  {hitRate}%
                </span>
              </div>
            ) : (
              <div className="w-[72px] h-[72px] rounded-full ring-1 ring-white/5 flex items-center justify-center shrink-0">
                <span className="text-white/20 text-[10px]">—</span>
              </div>
            )}
            <div className="flex-1 space-y-2.5">
              {size != null && (
                <div>
                  <p className="text-[10px] text-white/35 uppercase tracking-widest">Entries</p>
                  <p className={`text-xl font-bold tabular-nums ${tier.textAccent}`}>{size.toLocaleString()}</p>
                </div>
              )}
              {hitRate != null && (
                <div>
                  <p className="text-[10px] text-white/35 uppercase tracking-widest">Hit rate</p>
                  <p className="text-sm font-semibold text-white/70">{hitRate}%</p>
                </div>
              )}
              {hits == null && size == null && (
                <p className="text-[11px] text-white/25 italic">{available ? 'Stats not exposed' : 'Not connected'}</p>
              )}
            </div>
          </div>

          {/* Post-clear result badge */}
          <AnimatePresence>
            {result && (
              <motion.div
                key="result"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3, ease: EASE_OUT }}
                className={`flex items-center gap-2 text-[11px] px-3 py-2 rounded-xl font-medium ${
                  cleared ? 'bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20'
                  : errored ? 'bg-rose-500/10 text-rose-400 ring-1 ring-rose-500/20'
                  : 'bg-white/5 text-white/40'
                }`}
              >
                {cleared ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
                {cleared ? 'Cleared successfully' : result}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
}

// ─── Confirmation modal ────────────────────────────────────────────────────
function ConfirmModal({ onConfirm, onCancel, pending }: {
  onConfirm: () => void;
  onCancel: () => void;
  pending: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      style={{ backdropFilter: 'blur(16px)', background: 'rgba(0,0,0,0.75)' }}
    >
      <motion.div
        initial={{ scale: 0.92, y: 20, opacity: 0 }}
        animate={{ scale: 1, y: 0, opacity: 1 }}
        exit={{ scale: 0.94, y: 12, opacity: 0 }}
        transition={SPRING}
        className="relative w-full max-w-md"
      >
        {/* Outer shell */}
        <div className="p-[1.5px] rounded-[1.75rem] ring-1 ring-rose-500/20 bg-white/[0.02]"
          style={{ boxShadow: '0 0 60px rgba(239,68,68,0.12)' }}>
          <div className="rounded-[calc(1.75rem-1.5px)] px-8 py-8 space-y-6"
            style={{ background: 'rgba(10,10,14,0.95)' }}>
            {/* Close */}
            <button
              onClick={onCancel}
              className="absolute top-5 right-5 w-8 h-8 rounded-full bg-white/5 hover:bg-white/10 flex items-center justify-center text-white/40 hover:text-white/70 transition-colors duration-300"
            >
              <X className="w-4 h-4" />
            </button>

            {/* Icon */}
            <div className="w-14 h-14 rounded-2xl bg-rose-500/10 ring-1 ring-rose-500/20 flex items-center justify-center mx-auto"
              style={{ boxShadow: 'inset 0 1px 1px rgba(255,255,255,0.05)' }}>
              <Trash2 className="w-6 h-6 text-rose-400" strokeWidth={1.5} />
            </div>

            {/* Copy */}
            <div className="text-center space-y-2">
              <p className="text-[10px] uppercase tracking-[0.2em] text-rose-400 font-medium">Destructive Action</p>
              <h2 className="text-xl font-bold text-white/90">Invalidate all caches?</h2>
              <p className="text-sm text-white/40 leading-relaxed">
                This will flush the hot cache, Redis exact cache, and Qdrant semantic cache simultaneously.
                In-flight requests will hit the backend directly until caches warm up again.
              </p>
            </div>

            {/* Actions */}
            <div className="flex gap-3">
              <button
                onClick={onCancel}
                className="flex-1 py-3 rounded-full text-sm font-medium text-white/50 bg-white/5 hover:bg-white/8 ring-1 ring-white/10 transition-all duration-300 ease-[cubic-bezier(0.32,0.72,0,1)]"
              >
                Cancel
              </button>
              <button
                onClick={onConfirm}
                disabled={pending}
                className="flex-1 py-3 rounded-full text-sm font-bold text-white bg-rose-500/80 hover:bg-rose-500 ring-1 ring-rose-400/30 transition-all duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                style={{ boxShadow: '0 0 20px rgba(239,68,68,0.3)' }}
              >
                {pending ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <>
                    <Trash2 className="w-4 h-4" />
                    Yes, invalidate
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

// ─── Main page ─────────────────────────────────────────────────────────────
export default function CachePage() {
  const qc = useQueryClient();
  const [showConfirm, setShowConfirm] = useState(false);
  const [clearResults, setClearResults] = useState<Record<string, string>>({});

  const { data, isLoading, error, dataUpdatedAt } = useQuery<CacheMetrics>({
    queryKey: ['admin', 'cache-metrics'],
    queryFn: getCacheMetrics,
    refetchInterval: 20_000,
    staleTime: 10_000,
  });

  const { mutate: doFlush, isPending } = useMutation({
    mutationFn: clearCache,
    onSuccess: (res) => {
      setClearResults(res.tiers ?? {});
      setShowConfirm(false);
      qc.invalidateQueries({ queryKey: ['admin', 'cache-metrics'] });
    },
    onError: () => setShowConfirm(false),
  });

  const handleRefresh = useCallback(() => {
    qc.invalidateQueries({ queryKey: ['admin', 'cache-metrics'] });
  }, [qc]);

  const tiers = data?.tiers;
  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

  return (
    <>
      {/* Confirmation modal */}
      <AnimatePresence>
        {showConfirm && (
          <ConfirmModal
            onConfirm={() => doFlush()}
            onCancel={() => setShowConfirm(false)}
            pending={isPending}
          />
        )}
      </AnimatePresence>

      <div className="space-y-8">
        {/* ── Header ── */}
        <motion.div
          initial={{ opacity: 0, y: 16, filter: 'blur(4px)' }}
          animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
          transition={{ duration: 0.55, ease: EASE_OUT }}
          className="flex flex-col sm:flex-row sm:items-end justify-between gap-4"
        >
          <div>
            {/* Eyebrow */}
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] uppercase tracking-[0.2em] font-medium bg-white/5 ring-1 ring-white/10 text-white/40 mb-3">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              System
            </span>
            <h1 className="text-2xl font-bold text-white/90 tracking-tight">Cache Management</h1>
            <p className="text-sm text-white/35 mt-1">
              Monitor cache health and invalidate stale data after ingestion.
              {lastUpdated && <span className="ml-2 opacity-60">Updated {lastUpdated}</span>}
            </p>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-3 shrink-0">
            {/* Refresh */}
            <button
              onClick={handleRefresh}
              disabled={isLoading}
              className="group flex items-center gap-2 px-4 py-2.5 rounded-full text-sm font-medium text-white/50 bg-white/5 ring-1 ring-white/10 hover:ring-white/20 hover:text-white/80 transition-all duration-500 ease-[cubic-bezier(0.32,0.72,0,1)] active:scale-[0.97] disabled:opacity-40"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : 'group-hover:rotate-180 transition-transform duration-700'}`} />
              Refresh
            </button>

            {/* Invalidate — Button-in-Button architecture */}
            <button
              onClick={() => setShowConfirm(true)}
              className="group flex items-center gap-2.5 pl-5 pr-2 py-2.5 rounded-full text-sm font-semibold text-white bg-rose-500/75 ring-1 ring-rose-400/30 hover:bg-rose-500/90 transition-all duration-500 ease-[cubic-bezier(0.32,0.72,0,1)] active:scale-[0.97]"
              style={{ boxShadow: '0 0 24px rgba(239,68,68,0.25)' }}
            >
              Invalidate All
              {/* Nested icon island */}
              <span className="w-7 h-7 rounded-full bg-black/20 group-hover:bg-black/30 flex items-center justify-center transition-all duration-500 group-hover:translate-x-0.5 group-hover:-translate-y-[1px]">
                <Trash2 className="w-3.5 h-3.5" strokeWidth={2} />
              </span>
            </button>
          </div>
        </motion.div>

        {/* ── Error banner ── */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="flex items-center gap-3 px-5 py-4 rounded-2xl bg-rose-500/8 ring-1 ring-rose-500/20 text-rose-400 text-sm"
            >
              <AlertTriangle className="w-4 h-4 shrink-0" />
              Failed to load cache metrics — backend may be unreachable.
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Bento tier grid ── */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {TIERS.map((tier, idx) => (
            <TierCard
              key={tier.key}
              tier={tier}
              stats={tiers?.[tier.key] as Record<string, unknown> | undefined}
              result={clearResults[tier.key]}
              idx={idx}
            />
          ))}
        </div>

        {/* ── Post-ingestion note ── */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35, duration: 0.6, ease: EASE_OUT }}
          className="p-[1.5px] rounded-2xl ring-1 ring-white/5 bg-white/[0.01]"
        >
          <div
            className="rounded-[calc(1rem-1.5px)] px-6 py-5 flex items-start gap-4"
            style={{ background: 'rgba(10,10,14,0.7)' }}
          >
            <div className="w-8 h-8 rounded-xl bg-indigo-500/10 ring-1 ring-indigo-500/20 flex items-center justify-center shrink-0 mt-0.5">
              <Zap className="w-3.5 h-3.5 text-indigo-400" strokeWidth={1.5} />
            </div>
            <div className="space-y-1">
              <p className="text-[12px] font-semibold text-white/70">Auto-invalidation on ingestion</p>
              <p className="text-[11px] text-white/35 leading-relaxed max-w-2xl">
                The ingestion pipeline automatically flushes the exact and semantic cache tiers after each job completes.
                Manual invalidation here is only needed for hotfixes, model changes, or immediate post-deploy cache busting.
                The hot cache (in-process LRU) has a 5-minute TTL and self-expires.
              </p>
            </div>
          </div>
        </motion.div>
      </div>
    </>
  );
}
