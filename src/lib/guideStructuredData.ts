import type { GuideFaq } from '@/lib/guidesContent';

export interface GuideStructuredDataInput {
  canonicalUrl: string;
  headline: string;
  description: string;
  language: string;
  faqs: GuideFaq[];
  keywords?: string;
}

/**
 * Article + FAQPage graph for the public guides.
 *
 * One builder so both guides emit the same shape. The FAQ entries are the same
 * translated question/answer strings the page renders, not a second copy.
 * Nothing is invented: no publication dates, images, ratings, awards, teacher
 * quotations or affiliation claims.
 */
export function buildGuideStructuredData({
  canonicalUrl,
  headline,
  description,
  language,
  faqs,
  keywords,
}: GuideStructuredDataInput) {
  const origin = new URL(canonicalUrl).origin;
  const organizationId = `${origin}/#organization`;
  const siteId = `${origin}/#website`;
  const articleId = `${canonicalUrl}#article`;
  const faqId = `${canonicalUrl}#faq`;
  const inLanguage = (language || 'en').trim().toLowerCase();

  const publisher = {
    '@type': 'Organization',
    '@id': organizationId,
    name: 'AskMukthiGuru',
    url: origin,
  };

  return {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'Article',
        '@id': articleId,
        url: canonicalUrl,
        headline,
        description,
        inLanguage,
        ...(keywords ? { keywords } : {}),
        mainEntityOfPage: { '@type': 'WebPage', '@id': canonicalUrl },
        author: publisher,
        publisher,
        isPartOf: { '@id': siteId },
      },
      {
        '@type': 'FAQPage',
        '@id': faqId,
        inLanguage,
        isPartOf: { '@id': articleId },
        mainEntity: faqs.map((faq) => ({
          '@type': 'Question',
          name: faq.q,
          acceptedAnswer: { '@type': 'Answer', text: faq.a },
        })),
      },
    ],
  };
}
