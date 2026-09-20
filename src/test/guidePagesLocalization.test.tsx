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

  it('renders BeautifulStateMeditationPage in Telugu and Urdu', async () => {
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
      await changeUiLanguage('ur');
    });
    rerender(
      <MemoryRouter>
        <BeautifulStateMeditationPage />
      </MemoryRouter>
    );

    const urTitle = i18n.t('guides.beautifulStateMeditation.header.title');
    expect(urTitle).not.toEqual(teTitle);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(urTitle);
  });

  it('renders SelfCentricThinkingPage in Tamil and Punjabi', async () => {
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
      await changeUiLanguage('pa');
    });
    rerender(
      <MemoryRouter>
        <SelfCentricThinkingPage />
      </MemoryRouter>
    );

    const paTitle = i18n.t('guides.selfCentricThinking.header.title');
    expect(paTitle).not.toEqual(taTitle);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(paTitle);
  });

  it('renders SereneMindPracticePage in Kannada and Sanskrit', async () => {
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
      await changeUiLanguage('sa');
    });
    rerender(
      <MemoryRouter>
        <SereneMindPracticePage />
      </MemoryRouter>
    );

    const saTitle = i18n.t('guides.sereneMindPractice.header.title');
    expect(saTitle).not.toEqual(knTitle);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(saTitle);
  });

  it('renders SpiritualGuideForAnxietyPage in Bengali and Odia', async () => {
    await act(async () => {
      await changeUiLanguage('bn');
    });
    const { rerender } = render(
      <MemoryRouter>
        <SpiritualGuideForAnxietyPage />
      </MemoryRouter>
    );

    const bnTitle = i18n.t('guides.spiritualGuideForAnxiety.header.title');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(bnTitle);

    await act(async () => {
      await changeUiLanguage('or');
    });
    rerender(
      <MemoryRouter>
        <SpiritualGuideForAnxietyPage />
      </MemoryRouter>
    );

    const orTitle = i18n.t('guides.spiritualGuideForAnxiety.header.title');
    expect(orTitle).not.toEqual(bnTitle);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(orTitle);
  });

  it('renders SufferingToBeautifulStatePage in Gujarati, Malayalam and Assamese', async () => {
    await act(async () => {
      await changeUiLanguage('gu');
    });
    const { rerender } = render(
      <MemoryRouter>
        <SufferingToBeautifulStatePage />
      </MemoryRouter>
    );

    const guTitle = i18n.t('guides.sufferingToBeautifulState.header.title');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(guTitle);

    await act(async () => {
      await changeUiLanguage('ml');
    });
    rerender(
      <MemoryRouter>
        <SufferingToBeautifulStatePage />
      </MemoryRouter>
    );

    const mlTitle = i18n.t('guides.sufferingToBeautifulState.header.title');
    expect(mlTitle).not.toEqual(guTitle);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(mlTitle);

    await act(async () => {
      await changeUiLanguage('as');
    });
    rerender(
      <MemoryRouter>
        <SufferingToBeautifulStatePage />
      </MemoryRouter>
    );

    const asTitle = i18n.t('guides.sufferingToBeautifulState.header.title');
    expect(asTitle).not.toEqual(mlTitle);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(asTitle);
  });

  const ALL_LOCALES = ['en', 'hi', 'te', 'kn', 'ta', 'mr', 'bn', 'gu', 'ml', 'ur', 'pa', 'or', 'as', 'sa'] as const;

  it('renders all 6 guide page titles across all 14 supported locales without raw keys', async () => {
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
