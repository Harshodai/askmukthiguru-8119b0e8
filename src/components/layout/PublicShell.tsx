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
export const PublicShell = ({ children }: PublicShellProps) => (
  <div className="min-h-dvh bg-background flex flex-col">
    <Navbar />
    {/* Navbar is position:fixed (~80px); offset so page headings are not hidden behind it. */}
    <main className="flex-1 pt-20">{children}</main>
    <Footer />
  </div>
);

export default PublicShell;
