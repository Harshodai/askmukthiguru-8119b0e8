import { motion } from 'framer-motion';
import { ReactNode } from 'react';
import { Link } from 'react-router-dom';

export interface ActionCardProps {
  href?: string;
  to?: string;
  icon: ReactNode;
  eyebrow?: ReactNode;
  title: string;
  subtitle?: ReactNode;
  arrow?: ReactNode;
  className?: string;
  delay?: number;
}

const wrapperClass = 'group block glass-card p-4 rounded-2xl hover:shadow-lg transition-all hover:-translate-y-0.5';

export const ActionCard = ({
  href,
  to,
  icon,
  eyebrow,
  title,
  subtitle,
  arrow,
  className = wrapperClass,
  delay = 0.6,
}: ActionCardProps) => {
  const content = (
    <div className="flex items-center gap-3 text-left">
      <div className="w-12 h-12 rounded-xl bg-ojas/15 flex items-center justify-center shrink-0">
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        {eyebrow && (
          <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-muted-foreground">
            {eyebrow}
          </div>
        )}
        <p className="font-semibold text-foreground truncate">{title}</p>
        {subtitle && (
          <p className="text-xs text-muted-foreground inline-flex items-center gap-1 mt-0.5">{subtitle}</p>
        )}
      </div>
      {arrow && <div className="shrink-0">{arrow}</div>}
    </div>
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.5 }}
      className="mt-8 max-w-xl mx-auto"
    >
      {to ? (
        <Link to={to} className={className}>{content}</Link>
      ) : (
        <a href={href} className={className}>{content}</a>
      )}
    </motion.div>
  );
};
