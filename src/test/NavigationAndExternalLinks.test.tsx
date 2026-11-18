import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { WhatsAppButton } from '@/components/common/WhatsAppButton';
import { EkamLinkButton } from '@/components/common/EkamLinkButton';
import { Navbar } from '@/components/landing/Navbar';
import { MeetTheGurusSection } from '@/components/landing/MeetTheGurusSection';
import { Footer } from '@/components/landing/Footer';

// Mock UserMenu to simplify Navbar rendering
vi.mock('@/components/common/UserMenu', () => ({
  UserMenu: () => <div data-testid="user-menu-mock" />,
}));

describe('WhatsAppButton', () => {
  it('renders with default test id and links to wa.me with fallback number', () => {
    render(<WhatsAppButton />);
    const link = screen.getByTestId('whatsapp-action-button');
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href');
    expect(link.getAttribute('href')).toContain('https://wa.me/918008888888');
    expect(link.getAttribute('href')).toContain('text=Namaste%20Mukthi%20Guru');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(link.className).toContain('min-h-[44px]');
    expect(link.className).toContain('min-w-[44px]');
  });

  it('respects VITE_WHATSAPP_NUMBER environment variable', () => {
    vi.stubEnv('VITE_WHATSAPP_NUMBER', '+91 99999 88888');
    render(<WhatsAppButton data-testid="wa-custom" />);
    const link = screen.getByTestId('wa-custom');
    expect(link.getAttribute('href')).toContain('https://wa.me/919999988888');
    vi.unstubAllEnvs();
  });

  it('renders pill variant with accessible text', () => {
    render(<WhatsAppButton variant="pill" data-testid="wa-pill" />);
    const link = screen.getByTestId('wa-pill');
    expect(link).toBeInTheDocument();
    expect(link.textContent).toContain('WhatsApp');
    expect(link.className).toContain('rounded-full');
  });
});

describe('EkamLinkButton', () => {
  it('renders default icon variant linking to https://www.ekam.org', () => {
    render(<EkamLinkButton />);
    const link = screen.getByTestId('ekam-link-button');
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', 'https://www.ekam.org');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(link.className).toContain('min-h-[44px]');
    expect(link.className).toContain('min-w-[44px]');
  });

  it('renders pill variant with Ekam branding', () => {
    render(<EkamLinkButton variant="pill" data-testid="ekam-pill" />);
    const link = screen.getByTestId('ekam-pill');
    expect(link).toBeInTheDocument();
    expect(link.textContent).toContain('Ekam');
    expect(link).toHaveAttribute('href', 'https://www.ekam.org');
  });

  it('renders text variant', () => {
    render(<EkamLinkButton variant="text" data-testid="ekam-text" />);
    const link = screen.getByTestId('ekam-text');
    expect(link).toBeInTheDocument();
    expect(link.textContent).toContain('Ekam');
    expect(link).toHaveAttribute('href', 'https://www.ekam.org');
  });
});

describe('Navbar updates', () => {
  it('renders Ekam and WhatsApp buttons and does not render GetHelpNow', () => {
    render(
      <BrowserRouter>
        <Navbar />
      </BrowserRouter>,
    );

    // Assert Ekam button exists
    expect(screen.getByTestId('navbar-ekam-button')).toBeInTheDocument();
    expect(screen.getByTestId('navbar-ekam-button')).toHaveAttribute('href', 'https://www.ekam.org');

    // Assert exactly 1 WhatsApp button exists (no mobile/desktop duplication)
    const waButtons = screen.getAllByTestId('navbar-whatsapp-button');
    expect(waButtons).toHaveLength(1);
    expect(screen.queryByTestId('navbar-mobile-whatsapp-button')).not.toBeInTheDocument();

    // Assert GetHelpNow is removed
    expect(screen.queryByTestId('get-help-now')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /get help now/i })).not.toBeInTheDocument();
  });
});

describe('MeetTheGurusSection external Ekam link', () => {
  it('contains outbound verified link to ekam.org', () => {
    render(<MeetTheGurusSection />);
    const ekamLinks = screen.getAllByRole('link', { name: /ekam/i });
    const ekamOrgLink = ekamLinks.find((l) => l.getAttribute('href') === 'https://www.ekam.org');
    expect(ekamOrgLink).toBeDefined();
    expect(ekamOrgLink).toHaveAttribute('target', '_blank');
    expect(ekamOrgLink).toHaveAttribute('rel', 'noopener noreferrer');
  });
});

describe('Footer external Ekam link', () => {
  it('contains outbound link to ekam.org in resources', () => {
    render(
      <BrowserRouter>
        <Footer />
      </BrowserRouter>,
    );
    const ekamLink = screen.getByRole('link', { name: /ekam/i });
    expect(ekamLink).toHaveAttribute('href', 'https://www.ekam.org');
    expect(ekamLink).toHaveAttribute('target', '_blank');
    expect(ekamLink).toHaveAttribute('rel', 'noopener noreferrer');
  });
});
