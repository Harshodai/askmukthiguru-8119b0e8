import { ReactNode } from 'react';
import { Navbar } from '@/components/landing/Navbar';
import { Footer } from '@/components/landing/Footer';

interface PublicShellProps {
  children: ReactNode;
  title?: string;
}

/**
 * Public layout shell for pages that should be reachable without authentication.
 * Renders the marketing nav and footer but NOT the authenticated sidebar/UserMenu.
 * Auth policy is explicit: this shell never calls useRequireAuth.
 */
export const PublicShell = ({ children, title }: PublicShellProps) => (
  <div className="min-h-dvh bg-background flex flex-col">
    <Navbar />
    {title && (
      <div className="sr-only">
        <h1>{title}</h1>
      </div>
    )}
    <main className="flex-1">{children}</main>
    <Footer />
  </div>
);

export default PublicShell;
