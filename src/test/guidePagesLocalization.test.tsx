import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import i18n, { changeUiLanguage } from '@/i18n';
import AiSpiritualCompanionPage from '@/pages/guides/AiSpiritualCompanionPage';
import BeautifulStateMeditationPage from '@/pages/guides/BeautifulStateMeditationPage';
import SelfCentricThinkingPage from '@/pages/guides/SelfCentricThinkingPage';
import SereneMindPracticePage from '@/pages/guides/SereneMindPracticePage';
import SpiritualGuideForAnxietyPage from '@/pages/guides/SpiritualGuideForAnxietyPage';
import SufferingToBeautifulStatePage from '@/pages/guides/SufferingToBeautifulStatePage';

describe('Guide Pages Localization', () => {
  beforeEach(async () => {
    await act(async () => {
      await changeUiLanguage('en');
    });
  });

  it('renders AiSpiritualCompanionPage in English and translates to Hindi', async () => {
    const { rerender } = render(
      <MemoryRouter>
        <AiSpiritualCompanionPage />
      </MemoryRouter>
    );

    const enTitle = i18n.t('guides.aiSpiritualCompanion.header.title');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(enTitle);

    await act(async () => {
      await changeUiLanguage('hi');
    });
    rerender(
      <MemoryRouter>
        <AiSpiritualCompanionPage />
      </MemoryRouter>
    );

    const hiTitle = i18n.t('guides.aiSpiritualCompanion.header.title');
    expect(hiTitle).not.toEqual(enTitle);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(hiTitle);
  });

  it('renders BeautifulStateMeditationPage in Telugu and Marathi', async () => {
    await act(async () => {
      await changeUiLanguage('te');
    });
    const { rerender } = render(
      <MemoryRouter>
        <BeautifulStateMeditationPage />
      </MemoryRouter>
    );

    const teTitle = i18n.t('guides.beautifulStateMeditation.header.title');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(teTitle);

    await act(async () => {
      await changeUiLanguage('mr');
    });
    rerender(
      <MemoryRouter>
        <BeautifulStateMeditationPage />
      </MemoryRouter>
    );

    const mrTitle = i18n.t('guides.beautifulStateMeditation.header.title');
    expect(mrTitle).not.toEqual(teTitle);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(mrTitle);
  });

  it('renders SelfCentricThinkingPage in Tamil and Malayalam', async () => {
    await act(async () => {
      await changeUiLanguage('ta');
    });
    const { rerender } = render(
      <MemoryRouter>
        <SelfCentricThinkingPage />
      </MemoryRouter>
    );

    const taTitle = i18n.t('guides.selfCentricThinking.header.title');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(taTitle);

    await act(async () => {
      await changeUiLanguage('ml');
    });
    rerender(
      <MemoryRouter>
        <SelfCentricThinkingPage />
      </MemoryRouter>
    );

    const mlTitle = i18n.t('guides.selfCentricThinking.header.title');
    expect(mlTitle).not.toEqual(taTitle);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(mlTitle);
  });

  it('renders SereneMindPracticePage in Kannada and Hindi', async () => {
    await act(async () => {
      await changeUiLanguage('kn');
    });
    const { rerender } = render(
      <MemoryRouter>
        <SereneMindPracticePage />
      </MemoryRouter>
    );

    const knTitle = i18n.t('guides.sereneMindPractice.header.title');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(knTitle);

    await act(async () => {
      await changeUiLanguage('hi');
    });
    rerender(
      <MemoryRouter>
        <SereneMindPracticePage />
      </MemoryRouter>
    );

    const hiTitle = i18n.t('guides.sereneMindPractice.header.title');
    expect(hiTitle).not.toEqual(knTitle);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(hiTitle);
  });

  it('renders SpiritualGuideForAnxietyPage in Hindi and Telugu', async () => {
    await act(async () => {
      await changeUiLanguage('hi');
    });
    const { rerender } = render(
      <MemoryRouter>
        <SpiritualGuideForAnxietyPage />
      </MemoryRouter>
    );

    const hiTitle = i18n.t('guides.spiritualGuideForAnxiety.header.title');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(hiTitle);

    await act(async () => {
      await changeUiLanguage('te');
    });
    rerender(
      <MemoryRouter>
        <SpiritualGuideForAnxietyPage />
      </MemoryRouter>
    );

    const teTitle = i18n.t('guides.spiritualGuideForAnxiety.header.title');
    expect(teTitle).not.toEqual(hiTitle);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(teTitle);
  });

  it('renders SufferingToBeautifulStatePage in Kannada and Malayalam', async () => {
    await act(async () => {
      await changeUiLanguage('kn');
    });
    const { rerender } = render(
      <MemoryRouter>
        <SufferingToBeautifulStatePage />
      </MemoryRouter>
    );

    const knTitle = i18n.t('guides.sufferingToBeautifulState.header.title');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(knTitle);

    await act(async () => {
      await changeUiLanguage('ml');
    });
    rerender(
      <MemoryRouter>
        <SufferingToBeautifulStatePage />
      </MemoryRouter>
    );

    const mlTitle = i18n.t('guides.sufferingToBeautifulState.header.title');
    expect(mlTitle).not.toEqual(knTitle);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(mlTitle);
  });

  const ALL_LOCALES = ['en', 'hi', 'te', 'kn', 'ta', 'mr', 'ml'] as const;

  it('renders all 6 guide page titles across all 7 supported locales without raw keys', async () => {
    const guideKeys = [
      'guides.aiSpiritualCompanion.header.title',
      'guides.beautifulStateMeditation.header.title',
      'guides.selfCentricThinking.header.title',
      'guides.sereneMindPractice.header.title',
      'guides.spiritualGuideForAnxiety.header.title',
      'guides.sufferingToBeautifulState.header.title',
    ];

    for (const lng of ALL_LOCALES) {
      await act(async () => {
        await changeUiLanguage(lng);
      });

      for (const key of guideKeys) {
        const translated = i18n.t(key);
        expect(translated).not.toBe(key);
        expect(translated.length).toBeGreaterThan(0);
      }
    }
  });
});
