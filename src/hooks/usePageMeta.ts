import { useEffect } from 'react';

interface PageMeta {
  title: string;
  description?: string;
  canonical?: string;
}

/**
 * Lightweight per-route SEO. Sets <title>, meta description, and canonical URL
 * without pulling in react-helmet. Restores previous values on unmount so
 * route changes don't leak meta from an unmounted page.
 */
export function usePageMeta({ title, description, canonical }: PageMeta) {
  useEffect(() => {
    const prevTitle = document.title;
    const descEl = document.querySelector('meta[name="description"]') as HTMLMetaElement | null;
    const prevDesc = descEl?.content;

    document.title = title;
    if (description && descEl) descEl.content = description;

    let canonicalEl = document.querySelector('link[rel="canonical"]') as HTMLLinkElement | null;
    const prevCanonical = canonicalEl?.href;
    if (canonical) {
      if (!canonicalEl) {
        canonicalEl = document.createElement('link');
        canonicalEl.rel = 'canonical';
        document.head.appendChild(canonicalEl);
      }
      canonicalEl.href = canonical;
    }

    return () => {
      document.title = prevTitle;
      if (descEl && prevDesc !== undefined) descEl.content = prevDesc;
      if (canonicalEl && prevCanonical !== undefined) canonicalEl.href = prevCanonical;
    };
  }, [title, description, canonical]);
}
