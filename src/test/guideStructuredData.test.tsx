import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AiSpiritualCompanionPage from '@/pages/guides/AiSpiritualCompanionPage';
import SereneMindPracticePage from '@/pages/guides/SereneMindPracticePage';
import { buildGuideStructuredData } from '@/lib/guideStructuredData';
import { getAiSpiritualCompanionContent, getSereneMindPracticeContent } from '@/lib/guidesContent';

describe('guide structured data (JSON-LD)', () => {
  it('builds structured data with stable self-referencing identifiers and publisher metadata', () => {
    const data = buildGuideStructuredData({
      canonicalUrl: 'https://askmukthiguru.lovable.app/guides/test-guide',
      headline: 'Test Headline',
      description: 'Test Description',
      language: 'en',
      faqs: [
        { q: 'What is X?', a: 'X is Y.' },
        { q: 'How does Z work?', a: 'Z works by W.' },
      ],
      keywords: 'test, keywords',
    });

    expect(data['@context']).toBe('https://schema.org');
    const graph = data['@graph'];
    expect(graph).toHaveLength(2);

    const article = graph.find((item) => item['@type'] === 'Article') as any;
    expect(article).toBeDefined();
    expect(article['@id']).toBe('https://askmukthiguru.lovable.app/guides/test-guide#article');
    expect(article.url).toBe('https://askmukthiguru.lovable.app/guides/test-guide');
    expect(article.headline).toBe('Test Headline');
    expect(article.description).toBe('Test Description');
    expect(article.inLanguage).toBe('en');
    expect(article.keywords).toBe('test, keywords');
    expect(article.mainEntityOfPage).toEqual({
      '@type': 'WebPage',
      '@id': 'https://askmukthiguru.lovable.app/guides/test-guide',
    });
    expect(article.publisher).toEqual({
      '@type': 'Organization',
      '@id': 'https://askmukthiguru.lovable.app/#organization',
      name: 'AskMukthiGuru',
      url: 'https://askmukthiguru.lovable.app',
    });
    expect(article.isPartOf).toEqual({
      '@id': 'https://askmukthiguru.lovable.app/#website',
    });

    const faqPage = graph.find((item) => item['@type'] === 'FAQPage') as any;
    expect(faqPage).toBeDefined();
    expect(faqPage['@id']).toBe('https://askmukthiguru.lovable.app/guides/test-guide#faq');
    expect(faqPage.inLanguage).toBe('en');
    expect(faqPage.isPartOf).toEqual({
      '@id': 'https://askmukthiguru.lovable.app/guides/test-guide#article',
    });
    expect(faqPage.mainEntity).toEqual([
      {
        '@type': 'Question',
        name: 'What is X?',
        acceptedAnswer: { '@type': 'Answer', text: 'X is Y.' },
      },
      {
        '@type': 'Question',
        name: 'How does Z work?',
        acceptedAnswer: { '@type': 'Answer', text: 'Z works by W.' },
      },
    ]);

    // Forbidden fields must not exist
    expect(article.datePublished).toBeUndefined();
    expect(article.dateModified).toBeUndefined();
    expect(article.image).toBeUndefined();
    expect(article.aggregateRating).toBeUndefined();
    expect(article.review).toBeUndefined();
    expect(article.award).toBeUndefined();
  });

  it('renders AiSpiritualCompanionPage with matching visible FAQ text and valid JSON-LD script', () => {
    const { unmount, container } = render(
      <MemoryRouter>
        <AiSpiritualCompanionPage />
      </MemoryRouter>,
    );

    const script = document.head.querySelector<HTMLScriptElement>('script[data-page-meta="true"]');
    expect(script).not.toBeNull();
    const parsed = JSON.parse(script!.textContent || '{}');
    expect(parsed['@context']).toBe('https://schema.org');

    const graph = parsed['@graph'];
    const article = graph.find((x: any) => x['@type'] === 'Article');
    const faqPage = graph.find((x: any) => x['@type'] === 'FAQPage');

    expect(article['@id']).toMatch(/\/guides\/ai-spiritual-companion#article$/);
    expect(article.inLanguage).toBe('en');
    expect(article.publisher['@id']).toMatch(/#organization$/);
    expect(article.publisher.name).toBe('AskMukthiGuru');

    // Forbidden fields absent
    expect(article.datePublished).toBeUndefined();
    expect(article.dateModified).toBeUndefined();
    expect(article.image).toBeUndefined();
    expect(article.aggregateRating).toBeUndefined();

    // Verify FAQ matching visible DT / DD in the DOM
    const dts = Array.from(container.querySelectorAll('dt')).map((el) => el.textContent?.trim());
    const dds = Array.from(container.querySelectorAll('dd')).map((el) => el.textContent?.trim());

    expect(faqPage.mainEntity.length).toBe(dts.length);
    faqPage.mainEntity.forEach((faqItem: any, index: number) => {
      expect(faqItem.name).toBe(dts[index]);
      expect(faqItem.acceptedAnswer.text).toBe(dds[index]);
    });

    unmount();
  });

  it('renders SereneMindPracticePage with matching visible FAQ text and valid JSON-LD script', () => {
    const { unmount, container } = render(
      <MemoryRouter>
        <SereneMindPracticePage />
      </MemoryRouter>,
    );

    const script = document.head.querySelector<HTMLScriptElement>('script[data-page-meta="true"]');
    expect(script).not.toBeNull();
    const parsed = JSON.parse(script!.textContent || '{}');
    expect(parsed['@context']).toBe('https://schema.org');

    const graph = parsed['@graph'];
    const article = graph.find((x: any) => x['@type'] === 'Article');
    const faqPage = graph.find((x: any) => x['@type'] === 'FAQPage');

    expect(article['@id']).toMatch(/\/guides\/serene-mind-practice#article$/);
    expect(article.inLanguage).toBe('en');
    expect(article.publisher['@id']).toMatch(/#organization$/);
    expect(article.publisher.name).toBe('AskMukthiGuru');

    // Forbidden fields absent
    expect(article.datePublished).toBeUndefined();
    expect(article.dateModified).toBeUndefined();
    expect(article.image).toBeUndefined();
    expect(article.aggregateRating).toBeUndefined();

    // Verify FAQ matching visible DT / DD in the DOM
    const dts = Array.from(container.querySelectorAll('dt')).map((el) => el.textContent?.trim());
    const dds = Array.from(container.querySelectorAll('dd')).map((el) => el.textContent?.trim());

    expect(faqPage.mainEntity.length).toBe(dts.length);
    faqPage.mainEntity.forEach((faqItem: any, index: number) => {
      expect(faqItem.name).toBe(dts[index]);
      expect(faqItem.acceptedAnswer.text).toBe(dds[index]);
    });

    unmount();
  });
});
