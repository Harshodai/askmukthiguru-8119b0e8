#!/usr/bin/env node
/**
 * Build-time prerendering for SEO.
 * Injects per-route <title>, <meta description>, canonical, OG tags, JSON-LD
 * into the base dist/index.html template, writes to dist/<path>/index.html.
 *
 * Run AFTER vite build: node scripts/prerender-seo.mjs
 * nginx try_files serves prerendered files; falls back to SPA shell.
 *
 * The base dist/index.html is left intact as the SPA fallback for any
 * dynamic routes not in the ROUTES map.
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const DIST = join(ROOT, 'dist');
const BASE_HTML_PATH = join(DIST, 'index.html');

const BASE_URL = 'https://askmukthiguru.lovable.app';
const OG_IMAGE = `${BASE_URL}/og-image.png`;
const ORG_ID = `${BASE_URL}/#organization`;
const SITE_ID = `${BASE_URL}/#website`;

const ROUTES = [
  {
    path: '/',
    title: 'AskMukthiGuru — AI Spiritual Guide',
    description: 'AI-guided spiritual conversations rooted in the teachings of Sri Preethaji & Sri Krishnaji. Free, private, always available.',
    jsonLdType: 'WebSite',
  },
  {
    path: '/chat',
    title: 'Chat with the AI Spiritual Guru — AskMukthiGuru',
    description: "Ask Sri Preethaji & Sri Krishnaji's AI guru anything. Free, private, grounded in recorded doctrine.",
    jsonLdType: 'WebApplication',
  },
  {
    path: '/practices',
    title: 'Spiritual Practices — Soul Sync, Serene Mind, Beautiful State',
    description: 'Guided spiritual practices from Sri Preethaji & Sri Krishnaji: Soul Sync, Serene Mind, Beautiful State meditation, daily reflection.',
    jsonLdType: 'CollectionPage',
  },
  {
    path: '/practices/soul-sync',
    title: 'Soul Sync Practice — Step-by-Step Spiritual Technique',
    description: "Soul Sync: Sri Preethaji's signature practice to move from suffering state to beautiful state. Guided audio + written steps.",
    jsonLdType: 'Article',
  },
  {
    path: '/practices/serene-mind',
    title: 'Serene Mind Practice — Breath-Based Meditation',
    description: 'Serene Mind: a 3-minute breath practice to calm the nervous system and enter the beautiful state.',
    jsonLdType: 'Article',
  },
  {
    path: '/practices/beautiful-state',
    title: 'Beautiful State Meditation — Enter the Calm',
    description: 'The Beautiful State is a calm, connected, uncontracted inner condition. Learn the meditation that opens it.',
    jsonLdType: 'Article',
  },
  {
    path: '/practices/daily-reflection',
    title: 'Daily Reflection — Spiritual Contemplation Practice',
    description: "Daily reflection prompts grounded in Sri Preethaji & Sri Krishnaji's teachings to deepen self-inquiry.",
    jsonLdType: 'Article',
  },
  {
    path: '/guides/spirit-guides',
    title: 'Spirit Guides — AI, Gurus, and Spiritual Companionship',
    description: 'What is a spirit guide? How AI, human gurus, and inner guidance differ. Grounded in Sri Preethaji & Sri Krishnaji\'s teachings.',
    jsonLdType: 'Article',
  },
  {
    path: '/guides/ai-spiritual-companion',
    title: 'AI Spiritual Companion — 24/7 Guidance Grounded in Doctrine',
    description: 'How an AI spiritual companion differs from a chatbot: zero-hallucination, doctrine-grounded, always available.',
    jsonLdType: 'Article',
  },
  {
    path: '/guides/beautiful-state-meditation',
    title: 'Beautiful State Meditation — A Complete Guide',
    description: "Complete guide to the Beautiful State meditation: technique, benefits, and Sri Preethaji's teaching.",
    jsonLdType: 'Article',
  },
  {
    path: '/guides/serene-mind-practice',
    title: 'Serene Mind Practice — Calm the Mind in 3 Minutes',
    description: 'Serene Mind practice guide: 4-6 breath technique to regulate the nervous system and enter stillness.',
    jsonLdType: 'Article',
  },
  {
    path: '/guides/self-centric-thinking',
    title: 'Self-Centric Thinking — Recognize and Transcend',
    description: "Self-centric thinking creates suffering. Learn to recognize and transcend it through Sri Preethaji's teachings.",
    jsonLdType: 'Article',
  },
  {
    path: '/guides/spiritual-guide-for-anxiety',
    title: 'Spiritual Guide for Anxiety — Beyond Coping',
    description: 'A spiritual approach to anxiety: not coping but dissolving the suffering state through the beautiful state.',
    jsonLdType: 'Article',
  },
  {
    path: '/guides/suffering-to-beautiful-state',
    title: 'From Suffering to the Beautiful State — A Path',
    description: "The journey from suffering state to beautiful state: practices, teachings, and the AI guru's role.",
    jsonLdType: 'Article',
  },
  {
    path: '/auth',
    title: 'Sign In — AskMukthiGuru AI Spiritual Guide',
    description: 'Sign in to AskMukthiGuru to chat with the AI spiritual guide. Free, private, always available.',
    jsonLdType: 'WebPage',
  },
  {
    path: '/privacy',
    title: 'Privacy Policy — AskMukthiGuru',
    description: 'How AskMukthiGuru handles your data, conversations, and spiritual practice history.',
    jsonLdType: 'WebPage',
  },
  {
    path: '/terms',
    title: 'Terms of Service — AskMukthiGuru',
    description: 'Terms of service for AskMukthiGuru AI spiritual guide.',
    jsonLdType: 'WebPage',
  },
];

function canonicalFor(path) {
  return `${BASE_URL}${path === '/' ? '' : path}`;
}

function ogTypeFor(jsonLdType) {
  if (jsonLdType === 'Article') return 'article';
  return 'website';
}

function buildJsonLd(route) {
  const url = canonicalFor(route.path);
  const ctx = 'https://schema.org';
  const publisher = { '@type': 'Organization', name: 'AskMukthiGuru', '@id': ORG_ID };
  switch (route.jsonLdType) {
    case 'WebSite':
      return {
        '@context': ctx,
        '@type': 'WebSite',
        '@id': SITE_ID,
        name: 'AskMukthiGuru',
        url: BASE_URL,
        description: route.description,
        publisher: { '@id': ORG_ID },
        potentialAction: {
          '@type': 'SearchAction',
          target: `${BASE_URL}/chat?q={search_term_string}`,
          'query-input': 'required name=search_term_string',
        },
      };
    case 'WebApplication':
      return {
        '@context': ctx,
        '@type': 'WebApplication',
        name: 'AskMukthiGuru',
        url,
        description: route.description,
        applicationCategory: 'SpiritualApplication',
        operatingSystem: 'Web',
        offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
        publisher,
      };
    case 'CollectionPage':
      return {
        '@context': ctx,
        '@type': 'CollectionPage',
        '@id': `${url}#collection`,
        name: route.title,
        description: route.description,
        url,
        isPartOf: { '@id': SITE_ID },
        publisher,
      };
    case 'Article':
      return {
        '@context': ctx,
        '@type': 'Article',
        headline: route.title,
        description: route.description,
        url,
        image: OG_IMAGE,
        author: publisher,
        publisher,
        isPartOf: { '@id': SITE_ID },
        mainEntityOfPage: { '@type': 'WebPage', '@id': url },
      };
    case 'WebPage':
    default:
      return {
        '@context': ctx,
        '@type': 'WebPage',
        name: route.title,
        description: route.description,
        url,
        isPartOf: { '@id': SITE_ID },
        publisher,
      };
  }
}

function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function injectMeta(html, route) {
  const canonical = canonicalFor(route.path);
  const ogType = ogTypeFor(route.jsonLdType);
  const jsonLd = buildJsonLd(route);
  const jsonLdBlock = `<script type="application/ld+json" data-prerendered="true">${JSON.stringify(jsonLd)}</script>`;

  let out = html;

  // Remove any existing <link rel="canonical"> ... </link> or self-closing variant
  out = out.replace(/<link\s+rel=["']canonical["'][^>]*>\s*/gi, '');

  // Replace <title>...</title> with route title
  out = out.replace(/<title>[\s\S]*?<\/title>/i, `<title>${escapeHtml(route.title)}</title>`);

  // Replace existing meta description
  out = out.replace(
    /<meta\s+name=["']description["']\s+content=["'][^"']*["']\s*\/?>/i,
    `<meta name="description" content="${escapeHtml(route.description)}" />`,
  );

  // Replace OG tags (title, description, url, type). Use upsert pattern: replace if exists.
  const upsertMeta = (matcher, replacement) => {
    if (matcher.test(out)) {
      out = out.replace(matcher, replacement);
    }
  };

  upsertMeta(
    /<meta\s+property=["']og:title["']\s+content=["'][^"']*["']\s*\/?>/i,
    `<meta property="og:title" content="${escapeHtml(route.title)}" />`,
  );
  upsertMeta(
    /<meta\s+property=["']og:description["']\s+content=["'][^"']*["']\s*\/?>/i,
    `<meta property="og:description" content="${escapeHtml(route.description)}" />`,
  );
  upsertMeta(
    /<meta\s+property=["']og:url["']\s+content=["'][^"']*["']\s*\/?>/i,
    `<meta property="og:url" content="${canonical}" />`,
  );
  upsertMeta(
    /<meta\s+property=["']og:type["']\s+content=["'][^"']*["']\s*\/?>/i,
    `<meta property="og:type" content="${ogType}" />`,
  );

  // Twitter title/description (twitter:image already in base)
  upsertMeta(
    /<meta\s+name=["']twitter:title["']\s+content=["'][^"']*["']\s*\/?>/i,
    `<meta name="twitter:title" content="${escapeHtml(route.title)}" />`,
  );
  if (/<meta\s+name=["']twitter:description["']/i.test(out)) {
    out = out.replace(
      /<meta\s+name=["']twitter:description["']\s+content=["'][^"']*["']\s*\/?>/i,
      `<meta name="twitter:description" content="${escapeHtml(route.description)}" />`,
    );
  } else {
    out = out.replace(
      /(<meta\s+name=["']twitter:card["'][^>]*>)/i,
      `$1\n    <meta name="twitter:description" content="${escapeHtml(route.description)}" />`,
    );
  }

  // Remove any prerendered JSON-LD blocks from a prior run (idempotency)
  out = out.replace(/<script\s+type=["']application\/ld\+json["']\s+data-prerendered=["']true["'][^>]*>[\s\S]*?<\/script>\s*/gi, '');

  // Insert canonical link + route JSON-LD right before </head>
  const headInject = `    <link rel="canonical" href="${canonical}" />\n    ${jsonLdBlock}\n  </head>`;
  out = out.replace(/\s*<\/head>/i, `\n${headInject}`);

  return out;
}

function main() {
  if (!existsSync(BASE_HTML_PATH)) {
    console.error(`✗ ${BASE_HTML_PATH} not found. Run "vite build" first.`);
    process.exit(1);
  }
  const baseHtml = readFileSync(BASE_HTML_PATH, 'utf8');

  let count = 0;
  for (const route of ROUTES) {
    const outHtml = injectMeta(baseHtml, route);
    const outDir = route.path === '/' ? DIST : join(DIST, route.path);
    const outFile = join(outDir, 'index.html');
    mkdirSync(outDir, { recursive: true });
    writeFileSync(outFile, outHtml);
    count += 1;
    console.log(`✓ prerendered: ${route.path} → ${outFile.replace(ROOT + '/', '')}`);
  }
  console.log(`Done: ${count} routes prerendered (base dist/index.html preserved as SPA fallback).`);
}

main();