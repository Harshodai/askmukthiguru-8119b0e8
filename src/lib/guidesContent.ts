import type { TFunction } from 'i18next';

export interface GuideFaq {
  q: string;
  a: string;
}

export function getAiSpiritualCompanionContent(t: TFunction) {
  const faqs: GuideFaq[] = [
    { q: t('guides.aiSpiritualCompanion.faqs.q1'), a: t('guides.aiSpiritualCompanion.faqs.a1') },
    { q: t('guides.aiSpiritualCompanion.faqs.q2'), a: t('guides.aiSpiritualCompanion.faqs.a2') },
    { q: t('guides.aiSpiritualCompanion.faqs.q3'), a: t('guides.aiSpiritualCompanion.faqs.a3') },
    { q: t('guides.aiSpiritualCompanion.faqs.q4'), a: t('guides.aiSpiritualCompanion.faqs.a4') },
    { q: t('guides.aiSpiritualCompanion.faqs.q5'), a: t('guides.aiSpiritualCompanion.faqs.a5') },
  ];

  return {
    meta: {
      title: t('guides.aiSpiritualCompanion.meta.title'),
      description: t('guides.aiSpiritualCompanion.meta.description'),
      articleHeadline: t('guides.aiSpiritualCompanion.meta.articleHeadline'),
      articleDescription: t('guides.aiSpiritualCompanion.meta.articleDescription'),
      publicShellTitle: t('guides.aiSpiritualCompanion.meta.publicShellTitle'),
    },
    header: {
      title: t('guides.aiSpiritualCompanion.header.title'),
      subtitle: t('guides.aiSpiritualCompanion.header.subtitle'),
    },
    sections: [
      {
        title: t('guides.aiSpiritualCompanion.sections.whyTitle'),
        body: t('guides.aiSpiritualCompanion.sections.whyBody'),
      },
      {
        title: t('guides.aiSpiritualCompanion.sections.destinationTitle'),
        body: t('guides.aiSpiritualCompanion.sections.destinationBody'),
      },
      {
        title: t('guides.aiSpiritualCompanion.sections.groundedTitle'),
        body: t('guides.aiSpiritualCompanion.sections.groundedBody'),
      },
    ],
    steps: {
      heading: t('guides.aiSpiritualCompanion.steps.heading'),
      items: [
        {
          n: 1,
          title: t('guides.aiSpiritualCompanion.steps.step1Title'),
          body: t('guides.aiSpiritualCompanion.steps.step1Body'),
        },
        {
          n: 2,
          title: t('guides.aiSpiritualCompanion.steps.step2Title'),
          body: t('guides.aiSpiritualCompanion.steps.step2Body'),
        },
        {
          n: 3,
          title: t('guides.aiSpiritualCompanion.steps.step3Title'),
          body: t('guides.aiSpiritualCompanion.steps.step3Body'),
        },
        {
          n: 4,
          title: t('guides.aiSpiritualCompanion.steps.step4Title'),
          body: t('guides.aiSpiritualCompanion.steps.step4Body'),
        },
      ],
    },
    breathwork: {
      heading: t('guides.aiSpiritualCompanion.breathwork.heading'),
      body: t('guides.aiSpiritualCompanion.breathwork.body'),
    },
    faqs: {
      heading: t('guides.aiSpiritualCompanion.faqs.heading'),
      items: faqs,
    },
    cta: {
      heading: t('guides.aiSpiritualCompanion.cta.heading'),
      body: t('guides.aiSpiritualCompanion.cta.body'),
      chatButton: t('guides.aiSpiritualCompanion.cta.chatButton'),
      practiceButton: t('guides.aiSpiritualCompanion.cta.practiceButton'),
      exploreButton: t('guides.aiSpiritualCompanion.cta.exploreButton'),
    },
  };
}

export function getBeautifulStateMeditationContent(t: TFunction) {
  const faqs: GuideFaq[] = [
    { q: t('guides.beautifulStateMeditation.faqs.q1'), a: t('guides.beautifulStateMeditation.faqs.a1') },
    { q: t('guides.beautifulStateMeditation.faqs.q2'), a: t('guides.beautifulStateMeditation.faqs.a2') },
    { q: t('guides.beautifulStateMeditation.faqs.q3'), a: t('guides.beautifulStateMeditation.faqs.a3') },
    { q: t('guides.beautifulStateMeditation.faqs.q4'), a: t('guides.beautifulStateMeditation.faqs.a4') },
    { q: t('guides.beautifulStateMeditation.faqs.q5'), a: t('guides.beautifulStateMeditation.faqs.a5') },
  ];

  return {
    meta: {
      title: t('guides.beautifulStateMeditation.meta.title'),
      description: t('guides.beautifulStateMeditation.meta.description'),
      articleHeadline: t('guides.beautifulStateMeditation.meta.articleHeadline'),
      articleDescription: t('guides.beautifulStateMeditation.meta.articleDescription'),
      publicShellTitle: t('guides.beautifulStateMeditation.meta.publicShellTitle'),
    },
    header: {
      title: t('guides.beautifulStateMeditation.header.title'),
      subtitle: t('guides.beautifulStateMeditation.header.subtitle'),
    },
    whatIs: {
      heading: t('guides.beautifulStateMeditation.whatIs.heading'),
      body: t('guides.beautifulStateMeditation.whatIs.body'),
      vsTitle: t('guides.beautifulStateMeditation.whatIs.vsTitle'),
      vsBody: t('guides.beautifulStateMeditation.whatIs.vsBody'),
    },
    practice: {
      heading: t('guides.beautifulStateMeditation.practice.heading'),
      steps: [
        {
          title: t('guides.beautifulStateMeditation.practice.step1Title'),
          body: t('guides.beautifulStateMeditation.practice.step1Body'),
        },
        {
          title: t('guides.beautifulStateMeditation.practice.step2Title'),
          body: t('guides.beautifulStateMeditation.practice.step2Body'),
        },
        {
          title: t('guides.beautifulStateMeditation.practice.step3Title'),
          body: t('guides.beautifulStateMeditation.practice.step3Body'),
        },
        {
          title: t('guides.beautifulStateMeditation.practice.step4Title'),
          body: t('guides.beautifulStateMeditation.practice.step4Body'),
        },
        {
          title: t('guides.beautifulStateMeditation.practice.step5Title'),
          body: t('guides.beautifulStateMeditation.practice.step5Body'),
        },
      ],
    },
    threeMinute: {
      heading: t('guides.beautifulStateMeditation.threeMinute.heading'),
      min1Label: t('guides.beautifulStateMeditation.threeMinute.min1Label'),
      min1Body: t('guides.beautifulStateMeditation.threeMinute.min1Body'),
      min2Label: t('guides.beautifulStateMeditation.threeMinute.min2Label'),
      min2Body: t('guides.beautifulStateMeditation.threeMinute.min2Body'),
      min3Label: t('guides.beautifulStateMeditation.threeMinute.min3Label'),
      min3Body: t('guides.beautifulStateMeditation.threeMinute.min3Body'),
      footer: t('guides.beautifulStateMeditation.threeMinute.footer'),
    },
    harder: {
      heading: t('guides.beautifulStateMeditation.harder.heading'),
      body: t('guides.beautifulStateMeditation.harder.body'),
    },
    dailyLife: {
      heading: t('guides.beautifulStateMeditation.dailyLife.heading'),
      part1: t('guides.beautifulStateMeditation.dailyLife.part1'),
      browsePracticesLink: t('guides.beautifulStateMeditation.dailyLife.browsePracticesLink'),
      part2: t('guides.beautifulStateMeditation.dailyLife.part2'),
      aiCompanionLink: t('guides.beautifulStateMeditation.dailyLife.aiCompanionLink'),
      part3: t('guides.beautifulStateMeditation.dailyLife.part3'),
    },
    faqs: {
      heading: t('guides.beautifulStateMeditation.faqs.heading'),
      items: faqs,
    },
    cta: {
      heading: t('guides.beautifulStateMeditation.cta.heading'),
      body: t('guides.beautifulStateMeditation.cta.body'),
      startChat: t('guides.beautifulStateMeditation.cta.startChat'),
      learnSereneMind: t('guides.beautifulStateMeditation.cta.learnSereneMind'),
    },
  };
}

export function getSelfCentricThinkingContent(t: TFunction) {
  const faqs: GuideFaq[] = [
    { q: t('guides.selfCentricThinking.faqs.q1'), a: t('guides.selfCentricThinking.faqs.a1') },
    { q: t('guides.selfCentricThinking.faqs.q2'), a: t('guides.selfCentricThinking.faqs.a2') },
    { q: t('guides.selfCentricThinking.faqs.q3'), a: t('guides.selfCentricThinking.faqs.a3') },
    { q: t('guides.selfCentricThinking.faqs.q4'), a: t('guides.selfCentricThinking.faqs.a4') },
    { q: t('guides.selfCentricThinking.faqs.q5'), a: t('guides.selfCentricThinking.faqs.a5') },
  ];

  return {
    meta: {
      title: t('guides.selfCentricThinking.meta.title'),
      description: t('guides.selfCentricThinking.meta.description'),
      articleHeadline: t('guides.selfCentricThinking.meta.articleHeadline'),
      articleDescription: t('guides.selfCentricThinking.meta.articleDescription'),
      publicShellTitle: t('guides.selfCentricThinking.meta.publicShellTitle'),
    },
    header: {
      title: t('guides.selfCentricThinking.header.title'),
      subtitle: t('guides.selfCentricThinking.header.subtitle'),
    },
    whatIs: {
      heading: t('guides.selfCentricThinking.whatIs.heading'),
      body1: t('guides.selfCentricThinking.whatIs.body1'),
      showsUpHeading: t('guides.selfCentricThinking.whatIs.showsUpHeading'),
      items: [
        t('guides.selfCentricThinking.whatIs.item1'),
        t('guides.selfCentricThinking.whatIs.item2'),
        t('guides.selfCentricThinking.whatIs.item3'),
        t('guides.selfCentricThinking.whatIs.item4'),
        t('guides.selfCentricThinking.whatIs.item5'),
      ],
      body2: t('guides.selfCentricThinking.whatIs.body2'),
    },
    whyFuels: {
      heading: t('guides.selfCentricThinking.whyFuels.heading'),
      body1: t('guides.selfCentricThinking.whyFuels.body1'),
      trapHeading: t('guides.selfCentricThinking.whyFuels.trapHeading'),
      body2: t('guides.selfCentricThinking.whyFuels.body2'),
    },
    approach: {
      heading: t('guides.selfCentricThinking.approach.heading'),
      steps: [
        {
          title: t('guides.selfCentricThinking.approach.step1Title'),
          body: t('guides.selfCentricThinking.approach.step1Body'),
        },
        {
          title: t('guides.selfCentricThinking.approach.step2Title'),
          body: t('guides.selfCentricThinking.approach.step2Body'),
        },
        {
          title: t('guides.selfCentricThinking.approach.step3Title'),
          body: t('guides.selfCentricThinking.approach.step3Body'),
        },
        {
          title: t('guides.selfCentricThinking.approach.step4Title'),
          body: t('guides.selfCentricThinking.approach.step4Body'),
        },
        {
          title: t('guides.selfCentricThinking.approach.step5Title'),
          body: t('guides.selfCentricThinking.approach.step5Body'),
        },
      ],
    },
    replaces: {
      heading: t('guides.selfCentricThinking.replaces.heading'),
      body: t('guides.selfCentricThinking.replaces.body'),
    },
    dailyPractice: {
      heading: t('guides.selfCentricThinking.dailyPractice.heading'),
      part1: t('guides.selfCentricThinking.dailyPractice.part1'),
      explorePracticesLink: t('guides.selfCentricThinking.dailyPractice.explorePracticesLink'),
      part2: t('guides.selfCentricThinking.dailyPractice.part2'),
      sereneMindBreathLink: t('guides.selfCentricThinking.dailyPractice.sereneMindBreathLink'),
      part3: t('guides.selfCentricThinking.dailyPractice.part3'),
      aiCompanionLink: t('guides.selfCentricThinking.dailyPractice.aiCompanionLink'),
      part4: t('guides.selfCentricThinking.dailyPractice.part4'),
    },
    faqs: {
      heading: t('guides.selfCentricThinking.faqs.heading'),
      items: faqs,
    },
    cta: {
      heading: t('guides.selfCentricThinking.cta.heading'),
      body: t('guides.selfCentricThinking.cta.body'),
      chatButton: t('guides.selfCentricThinking.cta.chatButton'),
      beautifulStateButton: t('guides.selfCentricThinking.cta.beautifulStateButton'),
    },
  };
}

export function getSereneMindPracticeContent(t: TFunction) {
  const faqs: GuideFaq[] = [
    { q: t('guides.sereneMindPractice.faqs.q1'), a: t('guides.sereneMindPractice.faqs.a1') },
    { q: t('guides.sereneMindPractice.faqs.q2'), a: t('guides.sereneMindPractice.faqs.a2') },
    { q: t('guides.sereneMindPractice.faqs.q3'), a: t('guides.sereneMindPractice.faqs.a3') },
    { q: t('guides.sereneMindPractice.faqs.q4'), a: t('guides.sereneMindPractice.faqs.a4') },
    { q: t('guides.sereneMindPractice.faqs.q5'), a: t('guides.sereneMindPractice.faqs.a5') },
  ];

  return {
    meta: {
      title: t('guides.sereneMindPractice.meta.title'),
      description: t('guides.sereneMindPractice.meta.description'),
      articleHeadline: t('guides.sereneMindPractice.meta.articleHeadline'),
      articleDescription: t('guides.sereneMindPractice.meta.articleDescription'),
      publicShellTitle: t('guides.sereneMindPractice.meta.publicShellTitle'),
    },
    header: {
      title: t('guides.sereneMindPractice.header.title'),
      subtitle: t('guides.sereneMindPractice.header.subtitle'),
    },
    whatIs: {
      heading: t('guides.sereneMindPractice.whatIs.heading'),
      body: t('guides.sereneMindPractice.whatIs.body'),
      whyRateHeading: t('guides.sereneMindPractice.whatIs.whyRateHeading'),
      whyRateBody: t('guides.sereneMindPractice.whatIs.whyRateBody'),
    },
    steps: {
      heading: t('guides.sereneMindPractice.steps.heading'),
      items: [
        {
          title: t('guides.sereneMindPractice.steps.step1Title'),
          body: t('guides.sereneMindPractice.steps.step1Body'),
        },
        {
          title: t('guides.sereneMindPractice.steps.step2Title'),
          body: t('guides.sereneMindPractice.steps.step2Body'),
        },
        {
          title: t('guides.sereneMindPractice.steps.step3Title'),
          body: t('guides.sereneMindPractice.steps.step3Body'),
        },
        {
          title: t('guides.sereneMindPractice.steps.step4Title'),
          body: t('guides.sereneMindPractice.steps.step4Body'),
        },
        {
          title: t('guides.sereneMindPractice.steps.step5Title'),
          body: t('guides.sereneMindPractice.steps.step5Body'),
        },
      ],
    },
    whenToUse: {
      heading: t('guides.sereneMindPractice.whenToUse.heading'),
      items: [
        t('guides.sereneMindPractice.whenToUse.item1'),
        t('guides.sereneMindPractice.whenToUse.item2'),
        t('guides.sereneMindPractice.whenToUse.item3'),
        t('guides.sereneMindPractice.whenToUse.item4'),
        t('guides.sereneMindPractice.whenToUse.item5'),
      ],
      note: t('guides.sereneMindPractice.whenToUse.note'),
    },
    mistakes: {
      heading: t('guides.sereneMindPractice.mistakes.heading'),
      items: [
        {
          title: t('guides.sereneMindPractice.mistakes.item1Title'),
          body: t('guides.sereneMindPractice.mistakes.item1Body'),
        },
        {
          title: t('guides.sereneMindPractice.mistakes.item2Title'),
          body: t('guides.sereneMindPractice.mistakes.item2Body'),
        },
        {
          title: t('guides.sereneMindPractice.mistakes.item3Title'),
          body: t('guides.sereneMindPractice.mistakes.item3Body'),
        },
      ],
    },
    doorway: {
      heading: t('guides.sereneMindPractice.doorway.heading'),
      part1: t('guides.sereneMindPractice.doorway.part1'),
      beautifulStateLink: t('guides.sereneMindPractice.doorway.beautifulStateLink'),
      part2: t('guides.sereneMindPractice.doorway.part2'),
      findPracticesLink: t('guides.sereneMindPractice.doorway.findPracticesLink'),
      part3: t('guides.sereneMindPractice.doorway.part3'),
      aiCompanionLink: t('guides.sereneMindPractice.doorway.aiCompanionLink'),
      part4: t('guides.sereneMindPractice.doorway.part4'),
    },
    faqs: {
      heading: t('guides.sereneMindPractice.faqs.heading'),
      items: faqs,
    },
    cta: {
      heading: t('guides.sereneMindPractice.cta.heading'),
      body: t('guides.sereneMindPractice.cta.body'),
      chatButton: t('guides.sereneMindPractice.cta.chatButton'),
      exploreButton: t('guides.sereneMindPractice.cta.exploreButton'),
    },
  };
}

export function getSpiritualGuideForAnxietyContent(t: TFunction) {
  const faqs: GuideFaq[] = [
    { q: t('guides.spiritualGuideForAnxiety.faqs.q1'), a: t('guides.spiritualGuideForAnxiety.faqs.a1') },
    { q: t('guides.spiritualGuideForAnxiety.faqs.q2'), a: t('guides.spiritualGuideForAnxiety.faqs.a2') },
    { q: t('guides.spiritualGuideForAnxiety.faqs.q3'), a: t('guides.spiritualGuideForAnxiety.faqs.a3') },
    { q: t('guides.spiritualGuideForAnxiety.faqs.q4'), a: t('guides.spiritualGuideForAnxiety.faqs.a4') },
    { q: t('guides.spiritualGuideForAnxiety.faqs.q5'), a: t('guides.spiritualGuideForAnxiety.faqs.a5') },
  ];

  return {
    meta: {
      title: t('guides.spiritualGuideForAnxiety.meta.title'),
      description: t('guides.spiritualGuideForAnxiety.meta.description'),
      articleHeadline: t('guides.spiritualGuideForAnxiety.meta.articleHeadline'),
      articleDescription: t('guides.spiritualGuideForAnxiety.meta.articleDescription'),
      publicShellTitle: t('guides.spiritualGuideForAnxiety.meta.publicShellTitle'),
    },
    header: {
      title: t('guides.spiritualGuideForAnxiety.header.title'),
      subtitle: t('guides.spiritualGuideForAnxiety.header.subtitle'),
    },
    notInHead: {
      heading: t('guides.spiritualGuideForAnxiety.notInHead.heading'),
      part1: t('guides.spiritualGuideForAnxiety.notInHead.part1'),
      selfCentricLink: t('guides.spiritualGuideForAnxiety.notInHead.selfCentricLink'),
      part2: t('guides.spiritualGuideForAnxiety.notInHead.part2'),
      sufferingStateHeading: t('guides.spiritualGuideForAnxiety.notInHead.sufferingStateHeading'),
      sufferingStateBody: t('guides.spiritualGuideForAnxiety.notInHead.sufferingStateBody'),
    },
    howAiHelps: {
      heading: t('guides.spiritualGuideForAnxiety.howAiHelps.heading'),
      body1: t('guides.spiritualGuideForAnxiety.howAiHelps.body1'),
      practicalHeading: t('guides.spiritualGuideForAnxiety.howAiHelps.practicalHeading'),
      body2: t('guides.spiritualGuideForAnxiety.howAiHelps.body2'),
    },
    approach: {
      heading: t('guides.spiritualGuideForAnxiety.approach.heading'),
      steps: [
        {
          title: t('guides.spiritualGuideForAnxiety.approach.step1Title'),
          body: t('guides.spiritualGuideForAnxiety.approach.step1Body'),
        },
        {
          title: t('guides.spiritualGuideForAnxiety.approach.step2Title'),
          body: t('guides.spiritualGuideForAnxiety.approach.step2Body'),
        },
        {
          title: t('guides.spiritualGuideForAnxiety.approach.step3Title'),
          part1: t('guides.spiritualGuideForAnxiety.approach.step3Part1'),
          sereneMindLink: t('guides.spiritualGuideForAnxiety.approach.sereneMindLink'),
          part2: t('guides.spiritualGuideForAnxiety.approach.step3Part2'),
        },
        {
          title: t('guides.spiritualGuideForAnxiety.approach.step4Title'),
          body: t('guides.spiritualGuideForAnxiety.approach.step4Body'),
        },
      ],
    },
    movingToward: {
      heading: t('guides.spiritualGuideForAnxiety.movingToward.heading'),
      part1: t('guides.spiritualGuideForAnxiety.movingToward.part1'),
      beautifulStateLink: t('guides.spiritualGuideForAnxiety.movingToward.beautifulStateLink'),
      part2: t('guides.spiritualGuideForAnxiety.movingToward.part2'),
    },
    dailyPractice: {
      heading: t('guides.spiritualGuideForAnxiety.dailyPractice.heading'),
      part1: t('guides.spiritualGuideForAnxiety.dailyPractice.part1'),
      browsePracticesLink: t('guides.spiritualGuideForAnxiety.dailyPractice.browsePracticesLink'),
      part2: t('guides.spiritualGuideForAnxiety.dailyPractice.part2'),
    },
    faqs: {
      heading: t('guides.spiritualGuideForAnxiety.faqs.heading'),
      items: faqs,
    },
    cta: {
      heading: t('guides.spiritualGuideForAnxiety.cta.heading'),
      body: t('guides.spiritualGuideForAnxiety.cta.body'),
      chatButton: t('guides.spiritualGuideForAnxiety.cta.chatButton'),
      practicesButton: t('guides.spiritualGuideForAnxiety.cta.practicesButton'),
    },
  };
}

export function getSufferingToBeautifulStateContent(t: TFunction) {
  const faqs: GuideFaq[] = [
    { q: t('guides.sufferingToBeautifulState.faqs.q1'), a: t('guides.sufferingToBeautifulState.faqs.a1') },
    { q: t('guides.sufferingToBeautifulState.faqs.q2'), a: t('guides.sufferingToBeautifulState.faqs.a2') },
    { q: t('guides.sufferingToBeautifulState.faqs.q3'), a: t('guides.sufferingToBeautifulState.faqs.a3') },
    { q: t('guides.sufferingToBeautifulState.faqs.q4'), a: t('guides.sufferingToBeautifulState.faqs.a4') },
    { q: t('guides.sufferingToBeautifulState.faqs.q5'), a: t('guides.sufferingToBeautifulState.faqs.a5') },
  ];

  return {
    meta: {
      title: t('guides.sufferingToBeautifulState.meta.title'),
      description: t('guides.sufferingToBeautifulState.meta.description'),
      articleHeadline: t('guides.sufferingToBeautifulState.meta.articleHeadline'),
      articleDescription: t('guides.sufferingToBeautifulState.meta.articleDescription'),
      publicShellTitle: t('guides.sufferingToBeautifulState.meta.publicShellTitle'),
    },
    header: {
      title: t('guides.sufferingToBeautifulState.header.title'),
      subtitle: t('guides.sufferingToBeautifulState.header.subtitle'),
    },
    difference: {
      heading: t('guides.sufferingToBeautifulState.difference.heading'),
      body: t('guides.sufferingToBeautifulState.difference.body'),
      sameSituationHeading: t('guides.sufferingToBeautifulState.difference.sameSituationHeading'),
      sameSituationBody: t('guides.sufferingToBeautifulState.difference.sameSituationBody'),
    },
    whyDefault: {
      heading: t('guides.sufferingToBeautifulState.whyDefault.heading'),
      part1: t('guides.sufferingToBeautifulState.whyDefault.part1'),
      selfCentricLink: t('guides.sufferingToBeautifulState.whyDefault.selfCentricLink'),
      part2: t('guides.sufferingToBeautifulState.whyDefault.part2'),
    },
    steps: {
      heading: t('guides.sufferingToBeautifulState.steps.heading'),
      step1Title: t('guides.sufferingToBeautifulState.steps.step1Title'),
      step1Body: t('guides.sufferingToBeautifulState.steps.step1Body'),
      step2Title: t('guides.sufferingToBeautifulState.steps.step2Title'),
      step2Body: t('guides.sufferingToBeautifulState.steps.step2Body'),
      step3Title: t('guides.sufferingToBeautifulState.steps.step3Title'),
      step3Part1: t('guides.sufferingToBeautifulState.steps.step3Part1'),
      sereneMindLink: t('guides.sufferingToBeautifulState.steps.sereneMindLink'),
      step3Part2: t('guides.sufferingToBeautifulState.steps.step3Part2'),
      step4Title: t('guides.sufferingToBeautifulState.steps.step4Title'),
      step4Body: t('guides.sufferingToBeautifulState.steps.step4Body'),
      step5Title: t('guides.sufferingToBeautifulState.steps.step5Title'),
      step5Part1: t('guides.sufferingToBeautifulState.steps.step5Part1'),
      beautifulStateLink: t('guides.sufferingToBeautifulState.steps.beautifulStateLink'),
      step5Part2: t('guides.sufferingToBeautifulState.steps.step5Part2'),
    },
    whyTakesPractice: {
      heading: t('guides.sufferingToBeautifulState.whyTakesPractice.heading'),
      body: t('guides.sufferingToBeautifulState.whyTakesPractice.body'),
    },
    dailyHabit: {
      heading: t('guides.sufferingToBeautifulState.dailyHabit.heading'),
      part1: t('guides.sufferingToBeautifulState.dailyHabit.part1'),
      explorePracticesLink: t('guides.sufferingToBeautifulState.dailyHabit.explorePracticesLink'),
      part2: t('guides.sufferingToBeautifulState.dailyHabit.part2'),
    },
    faqs: {
      heading: t('guides.sufferingToBeautifulState.faqs.heading'),
      items: faqs,
    },
    cta: {
      heading: t('guides.sufferingToBeautifulState.cta.heading'),
      body: t('guides.sufferingToBeautifulState.cta.body'),
      chatButton: t('guides.sufferingToBeautifulState.cta.chatButton'),
      meditationButton: t('guides.sufferingToBeautifulState.cta.meditationButton'),
    },
  };
}
