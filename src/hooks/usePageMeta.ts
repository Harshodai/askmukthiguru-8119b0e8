import { useEffect } from 'react';

interface PageMeta {
  title: string;
  description?: string;
  canonical?: string;
  ogType?: 'website' | 'article' | 'video.other';
  jsonLd?: Record<string, unknown> | Record<string, unknown>[];
}

/**
 * Lightweight per-route SEO. Sets <title>, meta description, canonical URL,
 * Open Graph tags (title/description/url/type), and an optional JSON-LD
 * <script> block. Restores previous values on unmount so route changes
 * don't leak meta from an unmounted page.
 */
export function usePageMeta({ title, description, canonical, ogType = 'website', jsonLd }: PageMeta) {
  useEffect(() => {
    const prevTitle = document.title;
    document.title = title;

    const ensureMeta = (selector: string, create: () => HTMLMetaElement) => {
      let el = document.head.querySelector<HTMLMetaElement>(selector);
      if (!el) {
        el = create();
        document.head.appendChild(el);
      }
      return el;
    };

    const setMeta = (selector: string, attr: 'name' | 'property', key: string, value?: string) => {
      if (!value) return { el: null as HTMLMetaElement | null, prev: undefined as string | undefined, created: false };
      const existing = document.head.querySelector<HTMLMetaElement>(selector);
      const created = !existing;
      const el = ensureMeta(selector, () => {
        const m = document.createElement('meta');
        m.setAttribute(attr, key);
        return m;
      });
      const prev = el.content;
      el.content = value;
      return { el, prev, created };
    };

    const desc = setMeta('meta[name="description"]', 'name', 'description', description);
    const ogTitle = setMeta('meta[property="og:title"]', 'property', 'og:title', title);
    const ogDesc = setMeta('meta[property="og:description"]', 'property', 'og:description', description);
    const ogUrl = setMeta('meta[property="og:url"]', 'property', 'og:url', canonical);
    const ogTypeMeta = setMeta('meta[property="og:type"]', 'property', 'og:type', ogType);
    const twTitle = setMeta('meta[name="twitter:title"]', 'name', 'twitter:title', title);
    const twDesc = setMeta('meta[name="twitter:description"]', 'name', 'twitter:description', description);

    let canonicalEl = document.querySelector('link[rel="canonical"]') as HTMLLinkElement | null;
    const prevCanonical = canonicalEl?.href;
    let canonicalCreated = false;
    if (canonical) {
      if (!canonicalEl) {
        canonicalEl = document.createElement('link');
        canonicalEl.rel = 'canonical';
        document.head.appendChild(canonicalEl);
        canonicalCreated = true;
      }
      canonicalEl.href = canonical;
    }

    let jsonLdEl: HTMLScriptElement | null = null;
    if (jsonLd) {
      jsonLdEl = document.createElement('script');
      jsonLdEl.type = 'application/ld+json';
      jsonLdEl.dataset.pageMeta = 'true';
      jsonLdEl.text = JSON.stringify(jsonLd);
      document.head.appendChild(jsonLdEl);
    }

    return () => {
      document.title = prevTitle;
      const restore = (entry: { el: HTMLMetaElement | null; prev: string | undefined; created: boolean }) => {
        if (!entry.el) return;
        if (entry.created) entry.el.remove();
        else if (entry.prev !== undefined) entry.el.content = entry.prev;
      };
      restore(desc);
      restore(ogTitle);
      restore(ogDesc);
      restore(ogUrl);
      restore(ogTypeMeta);
      restore(twTitle);
      restore(twDesc);
      if (canonicalEl) {
        if (canonicalCreated) canonicalEl.remove();
        else if (prevCanonical !== undefined) canonicalEl.href = prevCanonical;
      }
      if (jsonLdEl) jsonLdEl.remove();
    };
  }, [title, description, canonical, ogType, JSON.stringify(jsonLd)]);
}
