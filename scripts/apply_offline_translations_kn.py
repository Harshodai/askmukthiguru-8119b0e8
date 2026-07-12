import json
from pathlib import Path

# --- Full Kannada Translations to fix remaining 55 issues ---
KN_ADDITIONAL_TRANSLATIONS = {
    "auth.forgotPassword": "ನಿಮ್ಮ ಪಾಸ್‌ವರ್ಡ್ ಮರೆತಿದ್ದೀರಾ?",
    "auth.hidePassword": "ಪಾಸ್‌ವರ್ಡ್ ಮರೆಮಾಚಿ",
    "auth.noAccount": "ಖಾತೆಯನ್ನು ಹೊಂದಿಲ್ಲವೇ?",
    "auth.pageDescription": "ಶ್ರೀ ಪ್ರೀತಾಜಿ ಮತ್ತು ಶ್ರೀ ಕೃಷ್ಣಾಜಿ ಅವರ ಬೋಧನೆಗಳಲ್ಲಿ ಬೇರೂರಿರುವ ನಿಮ್ಮ ಖಾಸಗಿ, AI-ಮಾರ್ಗದರ್ಶಿ ಆಧ್ಯಾತ್ಮಿಕ ಸಂಭಾಷಣೆಗಳನ್ನು ಮುಂದುವರಿಸಲು AskMukthiGuru ಗೆ ಸೈನ್ ಇನ್ ಮಾಡಿ.",
    "auth.profileSetupIncomplete": "ಪ್ರೊಫೈಲ್ ಸೆಟಪ್ ಅಪೂರ್ಣವಾಗಿದೆ",
    "chat.searchingTradition": "\"{{topic}}\" ನಲ್ಲಿ {{tradition}} ಅನ್ನು ಹುಡುಕಲಾಗುತ್ತಿದೆ…",
    "chat.switchLang": "ಸಂಭಾಷಣೆಯ ಭಾಷೆಯನ್ನು {{native}} ಗೆ ಬದಲಾಯಿಸುವುದೇ?",
    "chat.unlockedAssistant": "{{name}} ಅನ್‌ಲಾಕ್ ಮಾಡಲಾಗಿದೆ",
    "common.dataExportedDesc": "ನಿಮ್ಮ ಡೇಟಾವನ್ನು ಡೌನ್‌ಲೋಡ್ ಮಾಡಲಾಗಿದೆ.",
    "common.exportData": "ನನ್ನ ಡೇಟಾವನ್ನು ರಫ್ತು ಮಾಡಿ",
    "common.hideDetails": "ವಿವರಗಳನ್ನು ಮರೆಮಾಚಿ",
    "common.keep": "ಇರಿಸಿ",
    "landing.hero.badge": "ಪ್ರಾಚೀನ ಜ್ಞಾನದಿಂದ ಮಾರ್ಗದರ್ಶನ, AI ನಿಂದ ನಡೆಸಲ್ಪಡುತ್ತಿದೆ",
    "landing.hero.subtitle": "ದುಃಖದಿಂದ ನೆಮ್ಮದಿಗೆ ನಿಮ್ಮನ್ನು ಮುನ್ನಡೆಸಲು ವಿನ್ಯಾಸಗೊಳಿಸಲಾದ AI ಒಡನಾಡಿಯ ಮೂಲಕ ಶ್ರೀ ಪ್ರೀತಾಜಿ ಮತ್ತು ಶ್ರೀ ಕೃಷ್ಣಾಜಿ ಅವರ ಟೈಮ್‌ಲೆಸ್ ಜ್ಞಾನವನ್ನು ಅನುಭವಿಸಿ.",
    "landing.howItWorks.heading1": "ಹೇಗೆ",
    "landing.howItWorks.heading2": "ಕೆಲಸ ಮಾಡುತ್ತದೆ",
    "landing.howItWorks.step1Title": "ಸಂಭಾಷಣೆಯನ್ನು ಪ್ರಾರಂಭಿಸಿ",
    "landing.howItWorks.step3Desc": "ಶ್ರೀ ಪ್ರೀತಾಜಿ ಮತ್ತು ಶ್ರೀ ಕೃಷ್ಣಾಜಿ ಅವರ ಆಳವಾದ ಬೋಧನೆಗಳಲ್ಲಿ ಬೇರೂರಿರುವ ವೈಯಕ್ತಿಕ ಮಾರ್ಗದರ್ಶನವನ್ನು ಪಡೆಯಿರಿ.",
    "landing.howItWorks.subtitle": "ನೀವು ಎಲ್ಲಿದ್ದರೂ ನಿಮ್ಮ ಸುಂದರ ಸ್ಥಿತಿಗೆ ಸರಳ ಪ್ರಯಾಣ",
    "landing.howItWorks.videoPlaceholder": "ಅದನ್ನು ಕಾರ್ಯರೂಪದಲ್ಲಿ ನೋಡಿ (90 ಸೆಕೆಂಡುಗಳು)",
    "landing.meditation.benefit2": "ಭಾವನಾತ್ಮಕ ಒತ್ತಡವನ್ನು ಬಿಡುಗಡೆ ಮಾಡಿ",
    "landing.meditation.breathingCue": "4 ಎಣಿಕೆಗಳವರೆಗೆ ಉಸಿರನ್ನು ಒಳಗೆ ತೆಗೆದುಕೊಳ್ಳಿ... ತಡೆಹಿಡಿಯಿರಿ... 6 ಎಣಿಕೆಗಳವರೆಗೆ ಉಸಿರನ್ನು ಹೊರಬಿಡಿ",
    "landing.meditation.heading2": "ಸೆರೀನ್ ಮೈಂಡ್",
    "landing.meetGurus.description": "ಮೂರು ದಶಕಗಳಿಗೂ ಹೆಚ್ಚು ಕಾಲ, ಶ್ರೀ ಪ್ರೀತಾಜಿ ಮತ್ತು ಶ್ರೀ ಕೃಷ್ಣಾಜಿ ಲಕ್ಷಾಂತರ ಜನರನ್ನು ಆಂತರಿಕ ರೂಪಾಂತರದ ಕಡೆಗೆ ಮುನ್ನಡೆಸಿದ್ದಾರೆ. ಅವರ ಬೋಧನೆಗಳು ಪ್ರಾಚೀನ ಯೋಗ ಜ್ಞಾನವನ್ನು ಆಧುನಿಕ ನರವಿಜ್ಞಾನದೊಂದಿಗೆ ಸಂಯೋಜಿಸುವ ಪ್ರಜ್ಞೆಯ ತಂತ್ರಜ್ಞಾನದ ಮೂಲಕ 'ದುಃಖದ ಸ್ಥಿತಿ'ಯಿಂದ 'ಸುಂದರ ಸ್ಥಿತಿ'ಗೆ ಚಲಿಸುವುದರ ಮೇಲೆ ಕೇಂದ್ರೀಕರಿಸುತ್ತವೆ.",
    "landing.meetGurus.disclosure": "ಅವರ ಜ್ಞಾನದಿಂದ ಮಾರ್ಗದರ್ಶನ, AI ನಿಂದ ನಡೆಸಲ್ಪಡುತ್ತಿದೆ",
    "landing.meetGurus.quote": "\"ನೀವು ಸುಂದರ ಸ್ಥಿತಿಯಲ್ಲಿದ್ದಾಗ, ನಿಮ್ಮ ಸುತ್ತಲಿನ ಪ್ರತಿಯೊಬ್ಬರಿಗೂ ನೀವು ಆಶೀರ್ವಾದವಾಗುತ್ತೀರಿ. ನಿಮ್ಮ ಉಪಸ್ಥಿತಿಯೇ ಗುಣಪಡಿಸುತ್ತದೆ, ನಿಮ್ಮ ಮಾತುಗಳು ಸ್ಫೂರ್ತಿ ನೀಡುತ್ತವೆ ಮತ್ತು ನಿಮ್ಮ ಕಾರ್ಯಗಳು ರೂಪಾಂತರದ ಅಲೆಗಳನ್ನು ಸೃಷ್ಟಿಸುತ್ತವೆ.\"",
    "landing.practices.addFav": "ಮೆಚ್ಚಿನವುಗಳಿಗೆ ಸೇರಿಸಿ",
    "landing.practices.exploreAll": "ಎಲ್ಲಾ ಅಭ್ಯಾಸಗಳನ್ನು ಅನ್ವೇಷಿಸಿ",
    "landing.practices.removedDesc": "{{title}} ಅನ್ನು ನಿಮ್ಮ ಪಟ್ಟಿಯಿಂದ ತೆಗೆದುಹಾಕಲಾಗಿದೆ.",
    "landing.practices.removedFav": "ಮೆಚ್ಚಿನವುಗಳಿಂದ ತೆಗೆದುಹಾಕಲಾಗಿದೆ",
    "landing.practices.star": "{{title}} ಗೆ ಸ್ಟಾರ್ ಮಾಡಿ",
    "landing.practices.subtitle": "ಶ್ರೀ ಪ್ರೀತಾಜಿ ಮತ್ತು ಶ್ರೀ ಕೃಷ್ಣಾಜಿ ಅವರ ಬೋಧನೆಗಳಲ್ಲಿ ಬೇರೂರಿರುವ ಮಾರ್ಗದರ್ಶಿ ಧ್ಯಾನಗಳು. ಇಂದು ನಿಮಗೆ ಸೂಕ್ತವಾದುದನ್ನು ಆರಿಸಿ — ನಿಮ್ಮ ಮೆಚ್ಚಿನವುಗಳನ್ನು ಇಲ್ಲಿ ಪಿನ್ ಮಾಡಲು ಸ್ಟಾರ್ ಮಾಡಿ.",
    "landing.practices.unstar": "{{title}} ನಿಂದ ಸ್ಟಾರ್ ತೆಗೆದುಹಾಕಿ",
    "layout.navigate": "ನ್ಯಾವಿಗೇಟ್ ಮಾಡಿ",
    "meditation.guideStep4Title": "ಆಲೋಚನೆಯ ದಿಕ್ಕನ್ನು ಗಮನಿಸಿ",
    "meditation.guideStep5Title": "ಮಿದುಳಿನಲ್ಲಿ ಜ್ಯೋತಿ",
    "meditation.guideStepVideo1Title": "ಭಂಗಿ ಮತ್ತು ಉಸಿರಾಟ",
    "meditation.guideStepVideo2Desc": "ನಿಮ್ಮ ಆಂತರಿಕ ಭಾವನಾತ್ಮಕ ಸ್ಥಿತಿಯನ್ನು ಬದಲಾಯಿಸಲು ಪ್ರಯತ್ನಿಸದೆ ಅನುಭವಿಸಿ.",
    "meditation.guideStepVideo2Title": "ಭಾವನೆಯನ್ನು ಗಮನಿಸಿ",
    "meditation.guideStepVideo3Title": "ಆಲೋಚನೆಗಳನ್ನು ಗಮನಿಸಿ",
    "meditation.guideStepVideo5Desc": "ಜ್ಯೋತಿಯ ಮೇಲೆ ಗಮನವಿರಲಿ, ಮೃದುವಾಗಿ ನಕ್ಕು ಕಣ್ಣುಗಳನ್ನು ತೆರೆಯಿರಿ.",
    "meditation.guidedMeditation": "ಮಾರ್ಗದರ್ಶಿ ಧ್ಯಾನ",
    "meditation.hold": "ತಡೆಹಿಡಿಯಿರಿ",
    # 55 remaining Kannada keys
    "mood.bannerCta": "ಚೆಕ್ ಇನ್",
    "mood.calm": "ಶಾಂತ",
    "privacy.pageTitle": "ಗೌಪ್ಯತಾ ನೀತಿ — AskMukthiGuru",
    "privacy.pageDescription": "AskMukthiGuru ನಿಮ್ಮ ಡೇಟಾವನ್ನು ಹೇಗೆ ನಿರ್ವಹಿಸುತ್ತದೆ: ಕನಿಷ್ಠ ಸಂಗ್ರಹಣೆ, ಯಾವುದೇ ಮೂರನೇ ವ್ಯಕ್ತಿ ಹಂಚಿಕೆ ಇಲ್ಲ, ಮತ್ತು ಜಿಡಿಪಿಆರ್ ಅಡಿಯಲ್ಲಿ ಸಂಪೂರ್ಣ ರಫ್ತು ಮತ್ತು ಅಳಿಸುವಿಕೆ ಹಕ್ಕುಗಳು.",
    "privacy.title": "ಗೌಪ್ಯತಾ ನೀತಿ",
    "privacy.lastUpdated": "ಕೊನೆಯದಾಗಿ ನವೀಕರಿಸಲಾಗಿದೆ: {{date}}",
    "privacy.intro": "AskMukthiGuru ಗೌಪ್ಯತೆಗೆ ಮೊದಲ ಆದ್ಯತೆ ನೀಡುವ ಆಧ್ಯಾತ್ಮಿಕ ಒಡನಾಡಿಯಾಗಿದೆ. ದೃಢೀಕರಣಕ್ಕಾಗಿ ನಿಮ್ಮ ಇಮೇಲ್ ಮತ್ತು ಸಂಭಾಷಣೆಗಳನ್ನು ಮಾತ್ರ ನಾವು ಸಂಗ್ರಹಿಸುತ್ತೇವೆ.",
    "privacy.whatWeStore": "ನಾವು ಏನನ್ನು ಉಳಿಸುತ್ತೇವೆ",
    "privacy.storeEmail": "ಇಮೇಲ್ ವಿಳಾಸ ಮತ್ತು ಎನ್‌ಕ್ರಿಪ್ಟ್ ಮಾಡಿದ ಪಾಸ್‌ವರ್ಡ್ — ಸೈನ್-ಇನ್‌ಗಾಗಿ.",
    "privacy.neverSell": "ನಿಮ್ಮ ಡೇಟಾವನ್ನು ಮೂರನೇ ವ್ಯಕ್ತಿಗಳೊಂದಿಗೆ ಮಾರಾಟ ಮಾಡುವುದಿಲ್ಲ ಅಥವಾ ಹಂಚಿಕೊಳ್ಳುವುದಿಲ್ಲ.",
    "privacy.neverTrain": "ಹೊರಗಿನ ಮಾದರಿಗಳಿಗೆ ತರಬೇತಿ ನೀಡಲು ನಿಮ್ಮ ಸಂಭಾಷಣೆಗಳನ್ನು ಬಳಸುವುದಿಲ್ಲ.",
    "privacy.neverAds": "ನಿಮಗೆ ಜಾಹೀರಾತುಗಳನ್ನು ತೋರಿಸುವುದಿಲ್ಲ.",
    "privacy.aiDisclosureText": "ಪ್ರತಿಕ್ರಿಯೆಗಳನ್ನು ಶ್ರೀ ಪ್ರೀತಾಜಿ ಮತ್ತು ಶ್ರೀ ಕೃಷ್ಣಾಜಿ ಅವರ ಬೋಧನೆಗಳ ಆಧಾರದ ಮೇಲೆ AI ರಚಿಸಿದೆ. AskMukthiGuru ವೃತ್ತಿಪರ ಮಾನಸಿಕ ಆರೋಗ್ಯ ಕಾಳಜಿಗೆ ಪರ್ಯಾಯವಲ್ಲ.",
    "terms.pageTitle": "ಸೇವಾ ನಿಯಮಗಳು — AskMukthiGuru",
    "terms.title": "ಸೇವಾ ನಿಯಮಗಳು",
    "terms.notMedical": "ವೈದ್ಯಕೀಯ ಅಥವಾ ಮಾನಸಿಕ ಆರೋಗ್ಯ ಸಲಹೆಯಲ್ಲ",
    "terms.intellectualProperty": "ಬೌದ್ಧಿಕ ಆಸ್ತಿ",
    "terms.changesText": "ನಾವು ಈ ನಿಯಮಗಳನ್ನು ನವೀಕರಿಸಬಹುದು; ಬದಲಾವಣೆಯ ನಂತರದ ಬಳಕೆಯು ಹೊಸ ನಿಯಮಗಳ ಸ್ವೀಕಾರವನ್ನು ಸೂಚಿಸುತ್ತದೆ.",
    "terms.backToHome": "← ಮುಖಪುಟಕ್ಕೆ ಹಿಂತಿರುಗಿ",
    "meditation.pause": "ವಿರಾಮ",
    "meditation.obstacleTeacher": "ಪ್ರತಿಯೊಂದು ಅಡಚಣೆಯೂ ಒಬ್ಬ ಶಿಕ್ಷಕ ಎಂದು ಶ್ರೀ ಕೃಷ್ಣಾಜಿ ಬೋಧಿಸುತ್ತಾರೆ. ಮುಂದುವರಿಯಲು ದಯವಿಟ್ಟು ಸೆರೀನ್ ಮೈಂಡ್ ಧ್ಯಾನ ಮಾಡಿ.",
    "meditation.tabBreathe": "ಉಸಿರಾಟ",
    "meditation.tabVideo": "ವಿಡಿಯೋ",
    "meditation.tablistAria": "ಧ್ಯಾನದ ಮೋಡ್",
    "meditation.openInYoutube": "ಯೂಟ್ಯೂಬ್‌ನಲ್ಲಿ ವೀಕ್ಷಿಸಿ",
    "meditation.namaste": "ನಮಸ್ತೆ",
    "meditation.howDoYouFeel": "ನೀವು ಈಗ ಹೇಗೆ ಭಾವಿಸುತ್ತಿದ್ದೀರಿ?",
    "meditation.lighter": "ಹಗುರ",
    "meditation.whatInsightArose": "ಧ್ಯಾನದ ಸಮಯದಲ್ಲಿ ನಿಮಗೆ ಯಾವ ಒಳನೋಟ ಮೂಡಿತು?",
    "meditation.practiceComplete": "ನೀವು ನಿಮ್ಮ ಅಭ್ಯಾಸವನ್ನು ಪೂರ್ಣಗೊಳಿಸಿದ್ದೀರಿ. ಈ {{mood}} ಸ್ಥಿತಿಯನ್ನು ನಿಮ್ಮ ದಿನದಲ್ಲಿ ಕೊಂಡೊಯ್ಯಿರಿ.",
    "meditation.infusedFromTeaching": "{{teaching}} ಬೋಧನೆಯಿಂದ ಪ್ರೇರಿತವಾಗಿದೆ",
    "meditation.pauseAndClose": "ವಿರಾಮಗೊಳಿಸಿ ಮತ್ತು ಮುಚ್ಚಿ",
    "meditation.yourSoulJourney": "ನಿಮ್ಮ ಆತ್ಮದ ಪ್ರಯಾಣ",
    "meditation.stepXofY": "{{current}} ರ {{total}}",
    "memory.memory": "ನೆನಪು",
    "memory.coreSavedDesc": "ಗುರುಗಳು ಇದನ್ನು ಯಾವಾಗಲೂ ನಿಮ್ಮೊಂದಿಗೆ ಕೊಂಡೊಯ್ಯುತ್ತಾರೆ.",
    "memory.memorySaved": "ನೆನಪು ಉಳಿಸಲಾಗಿದೆ",
    "memory.couldNotSave": "ಉಳಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ",
    "memory.statMemories": "ನೆನಪುಗಳು",
    "memory.statCoreStatus": "ಕೋರ್ ಸ್ಥಿತಿ",
    "memory.coreMemory": "ಕೋರ್ ನೆನಪು",
    "memory.consciousnessMap": "ನನ್ನ ಪ್ರಜ್ಞೆಯ ನಕ್ಷೆ",
    "memory.listView": "ಪಟ್ಟಿ ವೀಕ್ಷಣೆ",
    "memory.fullscreenDesc": "ನಿಮ್ಮ ಸಂವಾದಾತ್ಮಕ ಪ್ರಜ್ಞೆಯ ನಕ್ಷೆಯ ಪೂರ್ಣ ಪರದೆಯ ನೋಟ.",
    "memory.saveMemory": "ನೆನಪನ್ನು ಉಳಿಸಿ",
    "memory.searchPlaceholder": "ನೆನಪುಗಳನ್ನು ಹುಡುಕಿ...",
    "memory.youAdded": "ನೀವು ಸೇರಿಸಿದ್ದು",
    "memory.autoExtracted": "ಸ್ವಯಂಚಾಲಿತವಾಗಿ ಹೊರತೆಗೆಯಲಾದ",
    "memory.forgetWarning": "ಗುರುಗಳು ಇನ್ನು ಮುಂದೆ ಭವಿಷ್ಯದ ಸಂಭಾಷಣೆಗಳಲ್ಲಿ ಇದನ್ನು ಉಲ್ಲೇಖಿಸುವುದಿಲ್ಲ. ಇದನ್ನು ಹಿಂತಿರುಗಿಸಲು ಸಾಧ್ಯವಿಲ್ಲ.",
    "memory.keep": "ಇರಿಸಿ",
    "memory.sessionReflections": "ಅಧಿವೇಶನದ ಪ್ರತಿಬಿಂಬಗಳು",
    "practices.title": "ಅಭ್ಯಾಸಗಳು",
    "practices.startPractice": "ಪ್ರಾರಂಭಿಸಿ",
    "practices.soulSync.purpose": "ಸೋಲ್ ಸಿಂಕ್ ನಿಮ್ಮ ಮನೆಗೆ ಹಿಂದಿರುಗುವ ಹಾದಿಯಾಗಿದೆ. ನೀವು ಕುಳಿತುಕೊಳ್ಳಿ, ಉಸಿರಾಡಿ, ಗುಂಜನ ಮಾಡಿ — ಮತ್ತು ದಿನದ ಗದ್ದಲವು ದೂರವಾಗುತ್ತದೆ. ಇದು ಸುಂದர ಸ್ಥಿತಿಗೆ ಪ್ರವೇಶ ದ್ವಾರವಾಗಿದೆ.",
    "practices.sereneMind.purpose": "ಭಾವನೆಗಳು ತೀವ್ರವಾಗಿದ್ದಾಗ ಮತ್ತು ಮನಸ್ಸು ಗೊಂದಲಕ್ಕೊಳಗಾದಾಗ, ನಿಮಗಾಗಿ ಮೂರು ನಿಮಿಷಗಳನ್ನು ನೀಡಿ. ಸೆರೀನ್ ಮೈಂಡ್ ಉದ್ವೇಗವನ್ನು ನಿವಾರಿಸುತ್ತದೆ ಮತ್ತು ನಿಮ್ಮನ್ನು ಶಾಂತ ಮನಸ್ಸಿಗೆ ಮರಳಿಸುತ್ತದೆ."
}

def main():
    locales_dir = Path("src/locales")
    lang_path = locales_dir / "kn.json"
    en_path = locales_dir / "en.json"
    
    with open(en_path, "r", encoding="utf-8") as f:
        en_data = json.load(f)
    
    def flatten_json(data, parent_key="", sep="."):
        items = {}
        for k, v in data.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(flatten_json(v, new_key, sep=sep))
            else:
                items[new_key] = v
        return items

    def unflatten_json(flat_data, sep="."):
        nested = {}
        for k, v in flat_data.items():
            parts = k.split(sep)
            curr = nested
            for part in parts[:-1]:
                if part not in curr:
                    curr[part] = {}
                if not isinstance(curr[part], dict):
                    curr[part] = {}
                curr = curr[part]
            curr[parts[-1]] = v
        return nested

    with open(lang_path, "r", encoding="utf-8") as f:
        tgt_data = json.load(f)
        
    tgt_flat = flatten_json(tgt_data)
    en_flat = flatten_json(en_data)
    
    # 1. Clean superfluous
    superfluous = set(tgt_flat.keys()) - set(en_flat.keys())
    for k in superfluous:
        del tgt_flat[k]
        
    # Apply our new Kannada translations
    for k, val in KN_ADDITIONAL_TRANSLATIONS.items():
        tgt_flat[k] = val
        
    # Let's check for any other remaining Devanagari in kn.json that we missed
    # and replace it with proper English fallback or translation if we can.
    def is_corrupted_kn(val):
        return any('\u0900' <= char <= '\u097F' for char in val)
        
    kannada_general_replacements = {
        "Admins": "ಆಡಳಿತಾಧಿಕಾರಿಗಳು",
        "Alerts": "ಎಚ್ಚರಿಕೆಗಳು",
        "Daily Teaching": "ದೈನಂದಿನ ಬೋಧನೆ",
        "Evaluations": "ಮೌಲ್ಯಮಾಪನಗಳು",
        "Feedback": "ಪ್ರತಿಕ್ರಿಯೆ",
        "Ingestion": "ಡೇಟಾ ಇಂಜೆಷನ್",
        "Jobs": "ಕೆಲಸಗಳು",
        "Admin Login": "ಅಡ್ಮಿನ್ ಲಾಗಿನ್",
        "OKF Manager": "OKF ವ್ಯವಸ್ಥಾಪಕ",
        "Overview": "ಅವಲೋಕನ",
        "Prompts": "ಪ್ರಾಂಪ್ಟ್‌ಗಳು",
        "Quality": "ಗುಣಮಟ್ಟ",
        "Queries": "ಪ್ರಶ್ನೆಗಳು",
        "RAG Flow": "RAG ಫ್ಲೋ",
        "Retrieval": "ಮಾಹಿತಿ ಮರುಪಡೆಯುವಿಕೆ",
        "Settings": "ಸೆಟ್ಟಿಂಗ್‌ಗಳು",
        "Teaching Tips": "ಬೋಧನಾ ಸಲಹೆಗಳು",
        "Triggers": "ಟ್ರಿಗ್ಗರ್‌ಗಳು",
        "Already have an account?": "ಈಗಾಗಲೇ ಖಾತೆ ಹೊಂದಿದ್ದೀರಾ?",
        " and ": " ಮತ್ತು ",
        "By continuing you agree to our": "ಮುಂದುವರಿಯುವ ಮೂಲಕ ನೀವು ನಮ್ಮ ಒಪ್ಪಂದಕ್ಕೆ ಒಪ್ಪುತ್ತೀರಿ",
        "Sign in": "ಸೈನ್ ಇನ್",
        "or": "ಅಥವಾ",
        "Sign out": "ಸೈನ್ ಔಟ್",
        "Reset password": "ಪಾಸ್‌ವರ್ಡ್ ಮರುಹೊಂದಿಸಿ",
        "Cancel": "ರದ್ದುಮಾಡಿ",
        "Done": "ಮುಗಿದಿದೆ",
        "Delete": "ಅಳಿಸಿ",
        "Confirm": "ಖಚಿತಪಡಿಸಿ",
        "Password": "ಪಾಸ್‌ವರ್ಡ್",
        "Save": "ಉಳಿಸಿ",
        "Next": "ಮುಂದೆ",
        "Back": "ಹಿಂದೆ",
        "Skip": "ಹೊರಗುಳಿಯಿರಿ",
        "Submit": "ಸಲ್ಲಿಸಿ",
        "Continue": "ಮುಂದುವರಿಯಿರಿ",
        "Help": "ಸಹಾಯ",
        "Home": "ಮುಖಪುಟ",
        "Settings": "ಸೆಟ್ಟಿಂಗ್‌ಗಳು",
        "Learn More": "ಹೆಚ್ಚು ತಿಳಿಯಿರಿ",
        "View All": "ಎಲ್ಲವನ್ನೂ ವೀಕ್ಷಿಸಿ",
        "Show more": "ಇನ್ನಷ್ಟು ತೋರಿಸು",
        "Show less": "ಕಡಿಮೆ ತೋರಿಸು",
        "No results found": "ಯಾವುದೇ ಫಲಿತಾಂಶಗಳು ಕಂಡುಬಂದಿಲ್ಲ",
        "Yes": "ಹೌದು",
        "No": "ಅಲ್ಲ",
        "Switch": "ಬದಲಾಯಿಸಿ",
        "Enable": "ಸಕ್ರಿಯಗೊಳಿಸಿ",
        "Disable": "ನಿಷ್ಕ್ರಿಯಗೊಳಿಸಿ",
        "Feedback": "ಪ್ರತಿಕ್ರಿಯೆ",
        "Menu": "ಮೆನು",
        "More": "ಇನ್ನಷ್ಟು",
        "Less": "ಕಡಿಮೆ",
        "On": "ಆನ್",
        "Off": "ಆಫ್"
    }

    for k, tgt_val in tgt_flat.items():
        if k not in en_flat:
            continue
        en_val = en_flat[k]
        
        # If it's corrupted (contains Devanagari) or still identical to English fallback
        if is_corrupted_kn(str(tgt_val)) or en_val == tgt_val:
            if en_val in kannada_general_replacements:
                tgt_flat[k] = kannada_general_replacements[en_val]

    # Save it back
    nested = unflatten_json(tgt_flat)
    with open(lang_path, "w", encoding="utf-8") as f:
        json.dump(nested, f, indent=2, ensure_ascii=False)
    print("Kannada locale updated with additional translations!")

if __name__ == "__main__":
    main()
