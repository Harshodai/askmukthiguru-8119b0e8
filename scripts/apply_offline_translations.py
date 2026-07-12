import json
import re
from pathlib import Path

# --- Hindi Translations ---
HI_TRANSLATIONS = {
    "practices.soulSync.howItWorks": [
        "सचेत श्वास — आराम से बैठें, अपने हाथों को अपनी जांघों पर रखें, हथेलियां ऊपर की ओर हों। आंखें बंद रखें। ८ धीमी, गहरी सांसें लें, अंगूठे से प्रत्येक उंगली (तर्जनी से कनिष्ठिका और वापस) को छूते हुए प्रत्येक सांस को गिनें।",
        "गुंजन तरंगें — तर्जनी और अंगूठे को एक साथ ज्ञान मुद्रा में लाएं। सांस छोड़ते हुए, मधुमक्खी की तरह धीरे से गुंजन करें (भ्रामरी प्राणायाम)। इसे ८ सांसों तक दोहराएं। अपने तंत्रिका तंत्र को शांत करने वाले कोमल स्पंदन को महसूस करें।",
        "मौन विराम में स्थिर हों — प्रत्येक श्वास लेने और छोड़ने के बीच, प्राकृतिक मौन में विश्राम करें। दबाव न डालें — बस साक्षी बनें।",
        "अहम् का जप — प्रत्येक श्वास छोड़ने के साथ, मन ही मन \"अहम्\" (मैं हूँ — असीम चेतना) फुसफुसाएं। अस्तित्व की सरल अनुभूति में विश्राम करें।",
        "विलीन और विस्तारित हों — अपने शरीर, कमरे और पूरे ब्रह्मांड को प्रकाश के एक असीम सुनहरे महासागर में विलीन और विस्तारित होते हुए देखें। महसूस करें कि आप और अस्तित्व अलग नहीं हैं।",
        "अपना संकल्प धारण करें — इस विस्तारित अवस्था में, अपने हृदय के संकल्प को मन में लाएं। इसके साकार होने की कल्पना करें। गहरी कृतज्ञता के साथ साधना समाप्त करें।"
    ],
    "auth.emailPlaceholder": "aap@example.com",
    "chat.copyUrlAria": "स्रोत {{number}} के लिए यूआरएल कॉपी करें",
    "chat.detectedLang": "{{name}} खोजी गई",
    "chat.drawingFrom": "{{tradition}} से लिया गया…",
    "chat.inviteCodePlaceholder": "sky-कोड...",
    "chat.noCitations": "कोई उद्धरण उपलब्ध नहीं है",
    "chat.savedToNotebookDesc": "\"{{title}}\" में जोड़ा गया",
    "chat.scheduledLanguages": "{{count}} अनुसूचित भाषाएं + अंग्रेजी",
    "chat.scrollToAnswerAria": "उत्तर {{number}} पर जाएं जहां यह स्रोत उद्धृत है",
    "chat.searchingTeachings": "\"{{topic}}\" पर शिक्षाओं की खोज की जा रही है…",
    "chat.searchingTradition": "\"{{topic}}\" पर {{tradition}} की खोज की जा रही है…",
    "chat.slashCommands": "स्लैश कमांड",
    "chat.slashKeyboardHint": "↑↓ नेविगेट करें · ↵ चुनें · esc बंद करें",
    "chat.slashResultsCount_one": "{{count}} परिणाम",
    "chat.sourcesReferences": "स्रोत और संदर्भ"
}

# --- Telugu Translations ---
TE_TRANSLATIONS = {
    "practices.soulSync.benefits": [
        "అమిగ్డాలాను ప్రశాంతపరుస్తుంది — కార్టిసాల్ మరియు ఒత్తిడిని తగ్గిస్తుంది.",
        "మెదడు తరంగాలను అధిక-బీటా (అతిగా ఆలోచించడం) నుండి పొందికైన ఆల్ఫా (ప్రశాంత ఏకాగ్రత) కు मారుస్తుంది.",
        "మీ అంతర్గత స్థితిని మీ సంకల్పంతో అనుసంధానిస్తుంది — సమకాలీకరణకు ద్వారాలు తెరుస్తుంది.",
        "స్వీయ-కేంద్రీకృత బాధాకరమైన స్థితులను కరిగిస్తుంది — ప్రేమ, అనుబంధం మరియు శాంతి కోసం హృదయాన్ని తెరుస్తుంది."
    ],
    "practices.soulSync.howItWorks": [
        "సచేతన శ్వాస — సౌకర్యవంతంగా కూర్చోండి, చేతులను మీ తొడలపై ఉంచండి, అరచేతులు పైకి ఉండాలి. కళ్ళు మూసుకోండి. బొటనవేలుతో ప్రతి వేలిని తాకుతూ (చూపుడు వేలు నుండి చిటికెన వేలు వరకు మరియు వెనక్కి) 8 నెమ్మదిగా, లోతైన శ్వాసలు తీసుకోండి.",
        "గుసగుసల కంపనం — చూపుడు వేలు మరియు బొటనవేలును జ్ఞాన ముద్రలో కలపండి. మీరు శ్వాస వదిలేటప్పుడు, తేనెటీగలా మెల్లగా గుసగుసలాడండి (భ్రామరీ ప్రాణాయామం). 8 శ్వాసల పాటు పునరావృతం చేయండి. మీ నాడీ వ్యవస్థను ప్రశాంతపరిచే సున్నితమైన కంపనాన్ని అనుభవించండి.",
        "నిశ్శబ్ద విరామంలో స్థిరపడండి — ప్రతి శ్వాస తీసుకోవడం మరియు వదలడం మధ్య ఉండే సహజ నిశ్శబ్దంలో విశ్రాంతి తీసుకోండి. బలవంతం చేయవద్దు — కేవలం సాక్షిగా ఉండండి.",
        "అహమ్ (Aham) జపించండి — ప్రతి శ్వాసను వదిలేటప్పుడు, మనస్సులో \"అహమ్\" (నేను — అపరిమిత చైతన్యాన్ని) అని జపించండి. ఉనికి యొక్క సాధారణ అనుభూతిలో విశ్రాంతి తీసుకోండి.",
        "కరిగి విస్తరించండి — మీ శరీరం, గది మరియు మొత్తం విశ్వం అనంతమైన బంగారు కాంతి సముద్రంలో కరిగిపోతున్నట్లుగా మరియు విస్తరిస్తున్నట్లుగా భావించండి. మీరు మరియు ఉనికి వేరు కాదని అనుభవించండి.",
        "మీ సంకల్పాన్ని నిలుపుకోండి — ఈ విస్తృత స్థితిలో, మీ హృదయపూర్వక సంకల్పాన్ని మనస్సులోకి తీసుకురండి. అది నెరవేరుతున్నట్లు ఊహించుకోండి. లోతైన కృతజ్ఞతతో ముగించండి."
    ],
    "auth.authFailed": "ధృవీకరణ విఫలమైంది. దయచేసి మళ్లీ ప్రయత్నించండి.",
    "auth.checkEmail": "మీ ఇమెయిల్ తనిఖీ చేయండి",
    "auth.couldNotConnectFacebookRetry": "ఫేస్‌బుక్‌కు కనెక్ట్ చేయలేకపోయాము. దయచేసి మళ్లీ ప్రయత్నించండి.",
    "auth.emailPlaceholder": "aap@example.com",
    "auth.enterEmailFirst": "మొదట మీ ఇమెయిల్ నమోదు చేయండి, ఆపై పాస్‌వర్డ్ మర్చిపోయారా క్లిక్ చేయండి.",
    "auth.oneTapFailed": "గూగుల్ వన్ ట్యాప్ సైన్-ఇన్ విఫలమైంది. దయచేసి మళ్లీ ప్రయత్నించండి.",
    "auth.or": "లేదా",
    "auth.pageTitle": "సైన్ ఇన్ చేయండి లేదా ఖాతాను సృష్టించండి — AskMukthiGuru",
    "auth.passwordResetSent": "మీ పాస్‌వర్డ్‌ను రీసెట్ చేయడానికి మేము మీకు ఒక లింక్‌ను పంపించాము.",
    "auth.returningFromGoogle": "గూగుల్ నుండి తిరిగి వస్తోంది...",
    "auth.signInProgress": "సైన్-ఇన్ ప్రక్రియ",
    "auth.signInTitle": "AskMukthiGuru లోకి సైన్ ఇన్ చేయండి",
    "auth.stepSignIn": "సైన్ ఇన్",
    "auth.troubleSigningIn": "సైన్ ఇన్ చేయడంలో ఇబ్బంది ఉందా?",
    "auth.tryAgain": "దయచేసి మళ్లీ ప్రయత్నించండి.",
    "auth.verificationSent": "సైన్-అప్ పూర్తి చేయడానికి మేము మీకు ఒక ధృవీకరణ లింక్‌ను పంపించాము. చిట్కా: పాత్ర మరియు ప్రొఫైల్ సెటప్‌ను ధృవీకరించడానికి సైన్ ఇన్ చేసిన తర్వాత /auth/diagnostics ని సందర్శించండి.",
    "auth.yourName": "మీ పేరు",
    "chat.drawingFrom": "{{tradition}} నుండి తీసుకుంటున్నాము…",
    "chat.inviteCodePlaceholder": "sky-కోడ్...",
    "chat.newMessagesShort": "{{count}} కొత్తవి",
    "onboarding.language.subtitle": "గురువు కోసం మీ ప్రాధాన్యత కలిగిన భాషను ఎంచుకోండి",
    "onboarding.language.continue": "కొనసాగించు",
    "meditation.practiceComplete": "మీరు మీ సాధనను పూర్తి చేసారు. ఈ {{mood}} స్థితిని మీ రోజంతా కొనసాగించండి.",
    "admin.admins": "అడ్మిన్లు",
    "admin.alerts": "హెచ్చరికలు",
    "admin.evals": "మూల్యాంకనాలు",
    "admin.login": "అడ్మిన్ లాగిన్",
    "admin.monitoring": "పర్యవేక్షణ",
    "admin.quality": "నాణ్యత",
    "admin.ragFlow": "రాగ్ ఫ్లో",
    "admin.retrieval": "తిరిగి పొందడం",
    "admin.teachingTips": "बोधना चिदकालु",
    "admin.telemetry": "టెలిమెట్రీ",
    "admin.unauthorized": "మీకు ఈ విభాగానికి ప్రాప్యత లేదు.",
    "desktopSidebar.deleteTitle": "సంభాషణను తొలగించాలా?",
    "desktopSidebar.deleteWarning": "ఈ చర్యను రద్దు చేయలేరు మరియు మీ బోధనా చరిత్ర కోల్పోతారు.",
    "desktopSidebar.gurusAlt": "గురువులు",
    "desktopSidebar.memories": "{{count}} జ్ఞాపకం",
    "desktopSidebar.memories_plural": "{{count}} జ్ఞాపకాలు",
    "desktopSidebar.newConvTooltip": "కొత్త సంభాషణ (విస్తరించడానికి ⌘B క్లిక్ చేయండి)",
    "desktopSidebar.noResults": "ఫలితాలు లేవు",
    "desktopSidebar.tagline": "మీ ఆధ్యాత్మిక సహచరుడు",
    "layout.aiService": "AI సేవ: {{mode}}",
    "layout.connectedMode": "గురువుతో అనుసంధానం చేయబడింది",
    "layout.offlineMode": "ఆఫ్‌లైన్ మోడ్",
    "layout.quick": "త్వరిత",
    "layout.sereneMindTitle": "సెరీన్ మైండ్ ధ్యానాన్ని ప్రారంభించండి",
    "layout.viewProfile": "ప్రొఫైల్ చూడండి",
    "memory.active": "క్రియాశీల",
    "memory.corePlaceholder": "ఉదా. నేను బెంగళూరులో సాఫ్ట్‌వేర్ ఇంజనీర్, 3 సంవత్సరాలుగా రోజువారీ ధ్యానిని, ఏకత్వ బోధనలను అన్వేషిస్తున్నాను...",
    "memory.coreSaved": "ప్రధాన జ్ఞాపకం భద్రపరచబడింది",
    "memory.couldNotForget": "మరచిపోలేకపోయాము",
    "memory.exitFullscreen": "పూర్తి స్క్రీన్ నుండి నిష్ಕ್ರమించు (Esc)",
    "memory.forgetAria": "ఈ జ్ఞాపకాన్ని మరచిపోండి",
    "memory.forgetBtn": "మరచిపో",
    "memory.forgotten": "మరచిపోయారు",
    "memory.graphView": "గ್ರಾಫ್ వీక్షణ",
    "memory.lastSaved": "చివరిగా సేవ్ చేయబడింది {{date}}",
    "memory.memories": "జ్ఞాపకాలు",
    "memory.memoryDesc": "మీ గురించి గురువు గుర్తుంచుకునే విషయాలు.",
    "memory.memorySavedDesc": "గురువు దీనిని గుర్తుంచుకుంటారు.",
    "memory.noMatchFound": "సరిపోలే జ్ఞాపకాలు ఏవీ కనుగొనబడలేదు.",
    "memory.noMemories": "ఇంకా జ్ఞాపకాలు ఏవీ లేవు.",
    "memory.statKgNodes": "KG నోడ్స్",
    "memory.statReflections": "ప్రతిబింబాలు",
    "memory.unset": "సెట్ చేయబడలేదు",
    "notes.bodyPlaceholder": "మీరు ఏమి అనుభవించారో, ఏమి గుర్తుంచుకోవాలనుకుంటున్నారో రాయండి...",
    "terms.accountTermination": "ఖాతా మరియు రద్దు",
    "terms.changes": "మార్పులు",
    "terms.intellectualPropertyText": "ఉదహరించిన బోధనలు శ్రీ ప్రీతాజీ, శ్రీ కృష్ణాజీ మరియు AUM ల యొక్క మేధో సంపత్తి, వీటిని ఇక్కడ విద్యా మరియు ప్రతిబింబ ప్రయోజనాల కోసం వారి గుర్తింపుతో ఉపయోగించబడ్డాయి."
}

# --- Kannada Translations ---
KN_TRANSLATIONS = {
    "practices.soulSync.benefits": [
        "ಅಮಿಗ್ಡಾಲಾವನ್ನು ಶಾಂತಗೊಳಿಸುತ್ತದೆ — ಕಾರ್ಟಿಸೋಲ್ ಮತ್ತು ಒತ್ತಡವನ್ನು ಕಡಿಮೆ ಮಾಡುತ್ತದೆ.",
        "ಮಿದುಳಿನ ತರಂಗಗಳನ್ನು ಹೆಚ್ಚಿನ ಬೀಟಾದಿಂದ ಸುಸಂಬದ್ಧ ಆಲ್ಫಾ ತರಂಗಗಳಿಗೆ ವರ್ಗಾಯಿಸುತ್ತದೆ.",
        "ನಿಮ್ಮ ಆಂತರಿಕ ಸ್ಥಿತಿಯನ್ನು ನಿಮ್ಮ ಸಂಕಲ್ಪದೊಂದಿಗೆ ಸಂಯೋಜಿಸುತ್ತದೆ — ಸಿಂಕ್ರೋನಿಸಿಟಿಗೆ ದಾರಿ ಮಾಡಿಕೊಡುತ್ತದೆ.",
        "ಸ್ವಯಂ-ಕೇಂದ್ರಿತ ದುಃಖದ ಸ್ಥಿತಿಗಳನ್ನು ಕರಗಿಸುತ್ತದೆ — ಪ್ರೀತಿ, ಸಂಪರ್ಕ ಮತ್ತು ಶಾಂತಿಗಾಗಿ ಹೃದಯವನ್ನು ಮುಕ್ತಗೊಳಿಸುತ್ತದೆ."
    ],
    "practices.soulSync.howItWorks": [
        "ಸಚೇತನ ಶ್ವಾಸ — ಆರಾಮವಾಗಿ ಕುಳಿತುಕೊಳ್ಳಿ, ಕೈಗಳನ್ನು ತೊಡೆಯ ಮೇಲೆ ಇರಿಸಿ, ಅಂಗೈಗಳು ಮೇಲಕ್ಕೆ ಮುಖ ಮಾಡಿರಲಿ. ಕಣ್ಣುಗಳನ್ನು ಮುಚ್ಚಿ. ಹೆಬ್ಬೆರಳಿನಿಂದ ಪ್ರತಿ ಬೆರಳನ್ನು ಸ್ಪರ್ಶಿಸುತ್ತಾ (ತರ್ಜನಿಯಿಂದ ಕಿರುಬೆರಳಿನವರೆಗೆ ಮತ್ತು ಹಿಂತಿರುಗಿ) 8 ನಿಧಾನವಾದ, ಆಳವಾದ ಉಸಿರಾಟವನ್ನು ತೆಗೆದುಕೊಳ್ಳಿ.",
        "ಗುಂಜನ ಕಂಪನ — ತರ್ಜನಿ ಮತ್ತು ಹೆಬ್ಬೆರಳನ್ನು ಜ್ಞಾನ ಮುದ್ರೆಯಲ್ಲಿ ಜೋಡಿಸಿ. ನೀವು ಉಸಿರನ್ನು ಹೊರಹಾಕುವಾಗ, ದುಂಬಿಯಂತೆ ಮೃದುವಾಗಿ ಗುಂಜನ ಮಾಡಿ (ಭ್ರಾಮರಿ ಪ್ರಾಣಾಯಾಮ). 8 ಉಸಿರಾಟದ ಚಕ್ರಗಳವರೆಗೆ ಪುನರಾವರ್ತಿಸಿ. ನಿಮ್ಮ ನರಮಂಡಲವನ್ನು ಶಾಂತಗೊಳಿಸುವ ಮೃದುವಾದ ಕಂಪನವನ್ನು ಅನುಭವಿಸಿ.",
        "ಮೌನ ವಿರಾಮದಲ್ಲಿ ನೆಲೆಸಿರಿ — ಪ್ರತಿ ಉಸಿರನ್ನು ತೆಗೆದುಕೊಳ್ಳುವ ಮತ್ತು ಬಿಡುವ ನಡುವೆ ಇರುವ ನೈಸರ್ಗಿಕ ಶಾಂತತೆಯಲ್ಲಿ ವಿಶ್ರಾಂತಿ ಪಡೆಯಿರಿ. ಒತ್ತಾಯಿಸಬೇಡಿ — ಕೇವಲ ಸಾಕ್ಷಿಯಾಗಿರಿ.",
        "\"ಅಹಂ\" (Aham) ಜಪಿಸಿ — ಪ್ರತಿ ಉಸಿರನ್ನು ಹೊರಹಾಕುವಾಗ, ಮನಸ್ಸಿನಲ್ಲಿ \"ಅಹಂ\" (ನಾನು — ಅನಂತ ಚೈತನ್ಯ) ಎಂದು ಜಪಿಸಿ. ಅಸ್ತಿತ್ವದ ಸರಳ ಅನುಭವದಲ್ಲಿ ವಿಶ್ರಮಿಸಿ.",
        "ಕರಗಿ ವಿಸ್ತರಿಸಿ — ನಿಮ್ಮ ದೇಹ, ಕೊಠಡಿ ಮತ್ತು ಇಡೀ ಬ್ರಹ್ಮಾಂಡವು ಶುದ್ಧ ಸುವರ್ಣ ಬೆಳಕಿನ ಅನಂತ ಸಾಗರದಲ್ಲಿ ಕರಗಿ ವಿಸ್ತರಿಸುತ್ತಿರುವುದನ್ನು ದೃಶ್ಯೀಕರಿಸಿ. ನೀವು ಮತ್ತು ಅಸ್ತಿತ್ವ ಬೇರೆಯಲ್ಲ ಎಂದು ಅನುಭವಿಸಿ.",
        "ನಿಮ್ಮ ಸಂಕಲ್ಪವನ್ನು ಹಿಡಿದುಕೊಳ್ಳಿ — ಈ ವಿಸ್ತೃತ ಸ್ಥಿತಿಯಲ್ಲಿ, ನಿಮ್ಮ ಹೃದಯಪೂರ್ವಕ ಸಂಕಲ್ಪವನ್ನು ಮನಸ್ಸಿಗೆ ತಂದುಕೊಳ್ಳಿ. ಅದು ಸಾಕಾರಗೊಳ್ಳುತ್ತಿರುವುದನ್ನು ದೃಶ್ಯೀಕರಿಸಿ. ಆಳವಾದ ಕೃತಜ್ಞತೆಯೊಂದಿಗೆ ಮುಗಿಸಿ."
    ],
    "practices.dailyReflection.benefits": [
        "ಕೃತಜ್ಞತೆಯನ್ನು ಬೆಳೆಸುತ್ತದೆ — ನಿಮ್ಮ ಗಮನವನ್ನು ಸಕಾರಾತ್ಮಕತೆಯ ಕಡೆಗೆ ತಿರುಗಿಸುತ್ತದೆ.",
        "ದಿನವನ್ನು ಎಚ್ಚರದಿಂದ ಕೊನೆಗೊಳಿಸಲು ಸಹಾಯ ಮಾಡುತ್ತದೆ — ಸಂಗ್ರಹವಾದ ಒತ್ತಡವನ್ನು ಬಿಡುಗಡೆ ಮಾಡುತ್ತದೆ.",
        "ನಿದ್ರೆಯ ಗುಣಮಟ್ಟವನ್ನು ಸುಧಾರಿಸುತ್ತದೆ — ಮಲಗುವ ಮುನ್ನ ಮನಸ್ಸನ್ನು ಶಾಂತಗೊಳಿಸುತ್ತದೆ.",
        "ಸ್ವಯಂ-ಕರುಣೆಯನ್ನು ಬೆಳೆಸುತ್ತದೆ — ತೀರ್ಪು ಇಲ್ಲದೆ ತಪ್ಪುಗಳನ್ನು ಮರುಪರಿಶೀಲಿಸಲು ಸಹಾಯ ಮಾಡುತ್ತದೆ."
    ],
    "practices.sereneMind.howItWorks": [
        "ಉಸಿರಾಟದ ಮೇಲೆ ಗಮನ ಕೇಂದ್ರೀಕರಿಸಿ — ಕಣ್ಣುಗಳನ್ನು ಮುಚ್ಚಿ, ನೇರವಾಗಿ ಕುಳಿತುಕೊಳ್ಳಿ. ನಿಮ್ಮ ಸಂಪೂರ್ಣ ಗಮನವನ್ನು ಮೂಗಿನ ಹೊಳ್ಳೆಗಳ ಮೂಲಕ ಒಳಹೋಗುವ ಮತ್ತು ಹೊರಹೋಗುವ ಉಸಿರಾಟದ ಮೇಲೆ ತಂದುಕೊಳ್ಳಿ.",
        "ನಿಮ್ಮ ಆಂತರಿಕ ಸ್ಥಿತಿಯನ್ನು ಗಮನಿಸಿ — ಪ್ರಸ್ತುತ ಇರುವ ಭಾವನೆಗಳು ಮತ್ತು ಆಲೋಚನೆಗಳನ್ನು ದೂರ ತಳ್ಳಲು ಪ್ರಯತ್ನಿಸದೆ ಗಮನಿಸಿ. ಕೇಳಿಕೊಳ್ಳಿ: \"ನಾನು ಈಗ ಯಾವ ನಿಖರವಾದ ಭಾವನೆಯನ್ನು ಅನುಭವಿಸುತ್ತಿದ್ದೇನೆ?\" (ಉದಾಹರಣೆಗೆ ಆತಂಕ, ಕೋಪ, ಉದಾಸೀನತೆ, ಶಾಂತಿ).",
        "ತೀರ್ಪು ಇಲ್ಲದೆ ಒಪ್ಪಿಕೊಳ್ಳಿ — ನೀವು ಅನುಭವಿಸುತ್ತಿರುವ ಭಾವನೆಯನ್ನು ಮೃದುವಾಗಿ ಹೆಸರಿಸಿ. ನಿಮ್ಮನ್ನು ನೀವೇ ತೀರ್ಪು ಮಾಡಬೇಡಿ, ಹೋರಾಡಬೇಡಿ. ಮೃದುವಾದ ಜಾಗೃತಿ ಇರಲಿ.",
        "ನಿಮ್ಮ ಮನಸ್ಸಿನ ಕೇಂದ್ರೀಕರಣವನ್ನು ಗಮನಿಸಿ — ನಿಮ್ಮ ಮನಸ್ಸು ಹಳೆಯ ಪಶ್ಚಾತ್ತಾಪಗಳು, ಭವಿಷ್ಯದ ಚಿಂತೆಗಳು ಅಥವಾ ಸ್ವಯಂ-ಕೇಂದ್ರಿತ ಆಲೋಚನೆಗಳಲ್ಲಿ ಮುಳುಗಿದೆಯೇ? ಈ ಪ್ರತ್ಯೇಕತೆಯ ಸ್ಥಿತಿಯನ್ನು ಒಪ್ಪಿಕೊಳ್ಳಿ.",
        "ಜ್ಯೋತಿ ದೃಶ್ಯೀಕರಣ — ನಿಮ್ಮ ಹುಬ್ಬುಗಳ ಮಧ್ಯದಲ್ಲಿ ಸ್ಥಿರವಾದ, ಸುವರ್ಣ ಜ್ಯೋತಿಯನ್ನು ಕಲ್ಪಿಸಿಕೊಳ್ಳಿ. ನಿಧಾನವಾಗಿ ಈ ಬೆಳಕನ್ನು ನಿಮ್ಮ ಮಿದುಳಿನ ಕೇಂದ್ರಕ್ಕೆ ಕರೆದೊಯ್ಯಿರಿ — ಅದು ಕತ್ತಲೆಯನ್ನು ಬೆಳಗಿಸಿ ಮನಸ್ಸಿಗೆ ಸ್ಥಿರತೆಯನ್ನು ತರಲಿ.",
        "ಹಾಸ್ಯದೊಂದಿಗೆ ಮುಗಿಸಿ — ನಿಮ್ಮ ಮುಖದ ಮೇಲೆ ಒಂದು ಮೃದುವಾದ, ಬೆಚ್ಚಗಿನ ನಗು ಇರಲಿ. ಕೊನೆಯ ಆಳವಾದ ಉಸಿರನ್ನು ತೆಗೆದುಕೊಳ್ಳಿ, ನಿಮ್ಮ ಸ್ಥಿತಿಯಲ್ಲಿನ ಬದಲಾವಣೆಯನ್ನು ಅನುಭವಿಸಿ, ಮತ್ತು ನಿಧಾನವಾಗಿ ಕಣ್ಣುಗಳನ್ನು ತೆರೆಯಿರಿ."
    ],
    "landing.meetGurus.tags": [
        "ಸ್ಥಾಪಕರು",
        "ಆಧ್ಯಾತ್ಮಿಕ ಗುರುಗಳು",
        "ಜ್ಞಾನೋದಯ ಹೊಂದಿದ ದಂಪತಿಗಳು"
    ],
    "admin.admins": "ಆಡಳಿತಾಧಿಕಾರಿಗಳು",
    "admin.dailyTeaching": "ದೈನಂದಿನ ಬೋಧನೆ",
    "admin.evals": "ಮೌಲ್ಯಮಾಪನಗಳು",
    "admin.feedback": "ಪ್ರತಿಕ್ರಿಯೆ",
    "admin.ingestion": "ಡೇಟಾ ಇಂಜೆಷನ್",
    "admin.jobs": "ಕೆಲಸಗಳು",
    "admin.login": "ಅಡ್ಮಿನ್ ಲಾಗಿನ್",
    "admin.okfManager": "OKF ವ್ಯವಸ್ಥಾಪಕ",
    "admin.overview": "ಅವಲೋಕನ",
    "admin.prompts": "ಪ್ರಾಂಪ್ಟ್‌ಗಳು",
    "admin.quality": "ಗುಣಮಟ್ಟ",
    "admin.queries": "ಪ್ರಶ್ನೆಗಳು",
    "admin.ragFlow": "RAG ಫ್ಲೋ",
    "admin.retrieval": "ಮಾಹಿತಿ ಮರುಪಡೆಯುವಿಕೆ",
    "admin.settings": "ಸೆಟ್ಟಿಂಗ್‌ಗಳು",
    "admin.teachingTips": "ಬೋಧನಾ ಸಲಹೆಗಳು",
    "admin.triggers": "ಟ್ರಿಗ್ಗರ್‌ಗಳು",
    "auth.alreadyAccount": "ಈಗಾಗಲೇ ಖಾತೆ ಹೊಂದಿದ್ದೀರಾ?",
    "auth.and": "ಮತ್ತು",
    "auth.byContinuing": "ಮುಂದುವರಿಯುವ ಮೂಲಕ",
    "auth.authTimeout": "ದೃಢೀಕರಣದ ಸಮಯಾವಕಾಶ ಮುಗಿದಿದೆ. ದಯವಿಟ್ಟು ಮತ್ತೊಮ್ಮೆ ಪ್ರಯತ್ನಿಸಿ.",
    "auth.connectingToGoogle": "ಗೂಗಲ್‌ಗೆ ಸಂಪರ್ಕಿಸಲಾಗುತ್ತಿದೆ...",
    "auth.continueWithFacebook": "ಫೇಸ್‌ಬುಕ್‌ನೊಂದಿಗೆ ಮುಂದುವರಿಯಿರಿ",
    "auth.createAccount": "ನಿಮ್ಮ ಖಾತೆಯನ್ನು ರಚಿಸಿ",
    "auth.email": "ಇಮೇಲ್",
    "auth.emailPlaceholder": "aap@example.com",
    "auth.enterEmailFirst": "ಮೊದಲು ನಿಮ್ಮ ಇಮೇಲ್ ಅನ್ನು ನಮೂದಿಸಿ, ನಂತರ ಮರೆತುಹೋದ ಪಾಸ್‌ವರ್ಡ್ ಅನ್ನು ಟ್ಯಾಪ್ ಮಾಡಿ.",
    "auth.oneTapFailed": "ಗೂಗಲ್ ಒನ್ ಟ್ಯಾಪ್ ಸೈನ್-ಇನ್ ವಿಫಲವಾಗಿದೆ. ದಯವಿಟ್ಟು ಮತ್ತೊಮ್ಮೆ ಪ್ರಯತ್ನಿಸಿ.",
    "auth.or": "ಅಥವಾ",
    "auth.pageTitle": "ಸೈನ್ ಇನ್ ಮಾಡಿ ಅಥವಾ ಖಾತೆಯನ್ನು ರಚಿಸಿ — AskMukthiGuru",
    "auth.passwordResetSent": "ನಿಮ್ಮ ಪಾಸ್‌ವರ್ಡ್ ಅನ್ನು ಮರುಹೊಂದಿಸಲು ನಾವು ನಿಮಗೆ ಲಿಂಕ್ ಕಳುಹಿಸಿದ್ದೇವೆ.",
    "auth.returningFromGoogle": "ಗೂಗಲ್‌ನಿಂದ ಹಿಂತಿರುಗಲಾಗುತ್ತಿದೆ...",
    "auth.signInProgress": "ಸೈನ್-ಇನ್ ಪ್ರಗತಿಯಲ್ಲಿದೆ",
    "auth.signInTitle": "AskMukthiGuru ಗೆ ಸೈನ್ ಇನ್ ಮಾಡಿ",
    "auth.stepSignIn": "ಸೈನ್ ಇನ್",
    "auth.troubleSigningIn": "ಸೈನ್ ಇನ್ ಮಾಡುವಲ್ಲಿ ತೊಂದರೆಯಾಗಿದೆಯೇ?",
    "auth.tryAgain": "ದಯವಿಟ್ಟು ಮತ್ತೊಮ್ಮೆ ಪ್ರಯತ್ನಿಸಿ.",
    "auth.verificationSent": "ಸೈನ್-ಅಪ್ ಪೂರ್ಣಗೊಳಿಸಲು ನಾವು ನಿಮಗೆ ಪರಿಶೀಲನೆ ಲಿಂಕ್ ಅನ್ನು ಕಳುಹಿಸಿದ್ದೇವೆ.",
    "auth.yourName": "ನಿಮ್ಮ ಹೆಸರು",
    "chat.drawingFrom": "{{tradition}} ನಿಂದ ತೆಗೆದುಕೊಳ್ಳಲಾಗುತ್ತಿದೆ...",
    "chat.inviteCodePlaceholder": "sky-ಕೋಡ್...",
    "chat.newMessagesShort": "{{count}} ಹೊಸ",
    "onboarding.language.subtitle": "ಗುರುಗಳಿಗಾಗಿ ನಿಮ್ಮ ಆದ್ಯತೆಯ ಭಾಷೆಯನ್ನು ಆರಿಸಿ",
    "onboarding.language.continue": "ಮುಂದುವರಿಯಿರಿ",
    "meditation.practiceComplete": "ನೀವು ನಿಮ್ಮ ಅಭ್ಯಾಸವನ್ನು ಪೂರ್ಣಗೊಳಿಸಿದ್ದೀರಿ. ಈ {{mood}} ಸ್ಥಿತಿಯನ್ನು ನಿಮ್ಮ दिनದಲ್ಲಿ ಕೊಂಡೊಯ್ಯಿರಿ.",
    "desktopSidebar.deleteTitle": "ಸಂಭಾಷಣೆಯನ್ನು ಅಳಿಸುವುದೇ?",
    "desktopSidebar.deleteWarning": "ಈ ಕ್ರಿಯೆಯನ್ನು ಹಿಂಪಡೆಯಲು ಸಾಧ್ಯವಿಲ್ಲ ಮತ್ತು ನಿಮ್ಮ ಬೋಧನೆಯ ಇತಿಹಾಸವು ಕಳೆದುಹೋಗುತ್ತದೆ.",
    "desktopSidebar.gurusAlt": "ಗುರುಗಳು",
    "desktopSidebar.memories": "{{count}} ನೆನಪು",
    "desktopSidebar.memories_plural": "{{count}} ನೆನಪುಗಳು",
    "desktopSidebar.newConvTooltip": "ಹೊಸ ಸಂಭಾಷಣೆ (ವಿಸ್ತರಿಸಲು ⌘B ಕ್ಲಿಕ್ ಮಾಡಿ)",
    "desktopSidebar.noResults": "ಯಾವುದೇ ಫಲಿತಾಂಶಗಳಿಲ್ಲ",
    "desktopSidebar.tagline": "ನಿಮ್ಮ ಆಧ್ಯಾತ್ಮಿಕ ಒಡನಾಡಿ",
    "layout.aiService": "AI ಸೇವೆ: {{mode}}",
    "layout.connectedMode": "ಗುರುಗಳೊಂದಿಗೆ ಸಂಪರ್ಕ ಹೊಂದಿದೆ",
    "layout.offlineMode": "ಆಫ್‌ಲೈನ್ ಮೋಡ್",
    "layout.quick": "ತ್ವರಿತ",
    "layout.sereneMindTitle": "ಸೆರೀನ್ ಮೈಂಡ್ ಧ್ಯಾನವನ್ನು ಪ್ರಾರಂಭಿಸಿ",
    "layout.viewProfile": "ಪ್ರೊಫೈಲ್ ವೀಕ್ಷಿಸಿ",
    "memory.active": "ಸಕ್ರಿಯ",
    "memory.corePlaceholder": "ಉದಾ. ನಾನು ಬೆಂಗಳೂರಿನಲ್ಲಿ ಸಾಫ್ಟ್‌ವೇರ್ ಎಂಜಿನಿಯರ್, 3 ವರ್ಷಗಳಿಂದ ದೈನಂದಿನ ಧ್ಯಾನಿ, ಏಕತ್ವ ಬೋಧನೆಗಳನ್ನು ಅನ್ವೇಷಿಸುತ್ತಿದ್ದೇನೆ...",
    "memory.coreSaved": "ಕೋರ್ ನೆನಪನ್ನು ಉಳಿಸಲಾಗಿದೆ",
    "memory.couldNotForget": "ಮರೆಯಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ",
    "memory.exitFullscreen": "ಪೂರ್ಣ ಪರದೆಯಿಂದ ನಿರ್ಗಮಿಸಿ (Esc)",
    "memory.forgetAria": "ಈ ನೆನಪನ್ನು ಮರೆತುಬಿಡಿ",
    "memory.forgetBtn": "ಮರೆತುಬಿಡಿ",
    "memory.forgotten": "ಮರೆತುಹೋಗಿದೆ",
    "memory.graphView": "ಗ್ರಾಫ್ ವೀಕ್ಷಣೆ",
    "memory.lastSaved": "ಕೊನೆಯದಾಗಿ ಉಳಿಸಲಾಗಿದೆ {{date}}",
    "memory.memories": "ನೆನಪುಗಳು",
    "memory.memoryDesc": "ಗುರುಗಳು ನಿಮ್ಮ ಬಗ್ಗೆ ನೆನಪಿಟ್ಟುಕೊಳ್ಳುವ ವಿಷಯಗಳು.",
    "memory.memorySavedDesc": "ಗುರುಗಳು ಇದನ್ನು ನೆನಪಿನಲ್ಲಿಡುತ್ತಾರೆ.",
    "memory.noMatchFound": "ಯಾವುದೇ ಹೊಂದಾಣಿಕೆಯ ನೆನಪುಗಳು ಕಂಡುಬಂದಿಲ್ಲ.",
    "memory.noMemories": "ಇನ್ನೇನೂ ನೆನಪುಗಳಿಲ್ಲ.",
    "memory.statKgNodes": "KG ನೋಡ್ಸ್",
    "memory.statReflections": "ಪ್ರತಿಬಿಂಬಗಳು",
    "memory.unset": "ಹೊಂದಿಸಲಾಗಿಲ್ಲ",
    "notes.bodyPlaceholder": "ನೀವು ಏನು ಅನುಭವಿಸಿದ್ದೀರಿ, ಏನನ್ನು ನೆನಪಿಟ್ಟುಕೊಳ್ಳಲು ಬಯಸುತ್ತೀರಿ ಎಂಬುದನ್ನು ಬರೆಯಿರಿ...",
    "terms.accountTermination": "ಖಾತೆ ಮತ್ತು ಮುಕ್ತಾಯ",
    "terms.changes": "ಬದಲಾವಣೆಗಳು",
    "terms.intellectualPropertyText": "ಉಲ್ಲೇಖಿಸಲಾದ ಬೋಧನೆಗಳು ಶ್ರೀ ಪ್ರೀತಾಜಿ, ಶ್ರೀ ಕೃಷ್ಣಾಜಿ ಮತ್ತು AUM ನ ಬೌದ್ಧಿಕ ಆಸ್ತಿಯಾಗಿದ್ದು, ಇಲ್ಲಿ ಶೈಕ್ಷಣಿಕ ಮತ್ತು ಪ್ರತಿಬಿಂಬದ ಉದ್ದೇಶಗಳಿಗಾಗಿ ಬಳಸಲಾಗಿದೆ."
}

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

def process_lang(lang, translation_map):
    locales_dir = Path("src/locales")
    en_path = locales_dir / "en.json"
    lang_path = locales_dir / f"{lang}.json"
    
    with open(en_path, "r", encoding="utf-8") as f:
        en_data = json.load(f)
    en_flat = flatten_json(en_data)
    
    tgt_flat = {}
    if lang_path.exists():
        with open(lang_path, "r", encoding="utf-8") as f:
            try:
                tgt_flat = flatten_json(json.load(f))
            except Exception as e:
                print(f"Error reading {lang}.json: {e}")
                tgt_flat = {}
                
    # 1. Clean superfluous keys
    superfluous = set(tgt_flat.keys()) - set(en_flat.keys())
    for k in superfluous:
        del tgt_flat[k]
        
    # 2. Add/merge missing, fallback, or corrupted keys
    for k, en_val in en_flat.items():
        # Check if we have an offline translation for this key
        if k in translation_map:
            tgt_flat[k] = translation_map[k]
        elif k not in tgt_flat:
            # Fallback to English value
            tgt_flat[k] = en_val
            
    # 3. Save back to target file
    nested = unflatten_json(tgt_flat)
    with open(lang_path, "w", encoding="utf-8") as f:
        json.dump(nested, f, indent=2, ensure_ascii=False)
    print(f"Updated {lang}.json successfully!")

def main():
    process_lang("hi", HI_TRANSLATIONS)
    process_lang("te", TE_TRANSLATIONS)
    process_lang("kn", KN_TRANSLATIONS)

if __name__ == "__main__":
    main()
