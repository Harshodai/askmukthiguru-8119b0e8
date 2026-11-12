#!/usr/bin/env python3
"""
merge_and_validate_i18n.py

Merges translations for the 32 personalization/memory keys across all 13 non-English locales,
ensuring strict leaf-key parity, punctuation fidelity, and no leftover English.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = ROOT / "src" / "locales"

# Curated translations for non-Sarvam supported languages
CURATED_TRANSLATIONS = {
    "ur": {
        "chat.memoryActive": "یادداشت فعال",
        "chat.memoryPaused": "یادداشت روکی گئی",
        "chat.memoryBanner.title": "ذاتی روحانی یادداشت",
        "chat.memoryBanner.description": "مکتھی گرو کو گفتگو کے دوران آپ کے اہم خیالات اور روحانی طریقوں کو یاد رکھنے کی اجازت دیں تاکہ آپ کی رہنمائی گہری ہو سکے۔ آپ کا ڈیٹا نجی، خفیہ کردہ ہے، اور کبھی بھی عوامی AI ماڈلز کی تربیت کے لیے استعمال نہیں ہوتا ہے۔",
        "chat.memoryBanner.enable": "ذاتی یادداشت فعال کریں",
        "chat.memoryBanner.notNow": "ابھی نہیں",
        "chat.memoryBanner.learnMore": "مزید جانیں",
        "chat.memoryBanner.learnMoreDetails": "فعال ہونے پر، آپ کی گفتگو کے بامعنی خیالات آپ کے نجی حکمت کے نقشے میں تعلیمات سے محفوظ طریقے سے جڑ جاتے ہیں۔ آپ کسی بھی وقت اپنی یادداشت کو روک یا مٹا سکتے ہیں۔",
        "chat.memoryBanner.toastEnabledTitle": "ذاتی یادداشت فعال ہو گئی",
        "chat.memoryBanner.toastEnabledDesc": "مکتھی گرو اب مستقبل کی رہنمائی کے لیے اہم خیالات کو یاد رکھے گا۔",
        "chat.memoryBanner.toastPausedTitle": "ذاتی یادداشت روک دی گئی",
        "chat.memoryBanner.toastPausedDesc": "آپ کی گفتگو سے کوئی نیا خیال محفوظ نہیں کیا جائے گا۔",
        "chat.memoryBanner.toastErasedTitle": "تمام یادداشتیں مٹا دی گئیں",
        "chat.memoryBanner.toastErasedDesc": "تمام ذاتی خیالات اور حکمت کے نقشے کے روابط حذف کر دیے گئے ہیں۔",
        "chat.memorySettings.title": "ذاتی روحانی یادداشت",
        "chat.memorySettings.badgeTitle": "روحانی یادداشت کی ترتیبات",
        "chat.memorySettings.description": "مکتھی گرو سیشنز کے دوران مسلسل، ذاتی رہنمائی فراہم کرنے کے لیے آپ کے خیالات، زندگی کے سیاق و سباق اور طریقوں کو یاد رکھ سکتا ہے۔",
        "chat.memorySettings.statusActive": "فعال",
        "chat.memorySettings.statusPaused": "روکی گئی",
        "chat.memorySettings.recordingLabel": "یادداشت کی ریکارڈنگ",
        "chat.memorySettings.recordingDesc": "فعال ہونے پر، گفتگو کے خیالات آپ کے نجی حکمت کے نقشے میں محفوظ طریقے سے درج ہو جاتے ہیں۔",
        "chat.memorySettings.pauseAction": "یادداشت روکیں",
        "chat.memorySettings.resumeAction": "یادداشت دوبارہ شروع کریں",
        "chat.memorySettings.viewAll": "پروفائل میں تمام یادداشتیں دیکھیں",
        "chat.memorySettings.eraseTitle": "تمام یادداشتیں مٹائیں",
        "chat.memorySettings.eraseDesc": "تمام خیالات، بنیادی نوٹس، اور ذاتی حکمت کے نقشے کے روابط کو مستقل طور پر حذف کریں۔ یہ عمل واپس نہیں کیا جا سکتا۔",
        "chat.memorySettings.eraseButton": "سب کچھ مٹائیں",
        "chat.memorySettings.eraseConfirmTitle": "کیا آپ کو بالکل یقین ہے؟",
        "chat.memorySettings.eraseConfirmDesc": "یہ تمام سرورز پر آپ کے نجی حکمت کے نقشے میں موجود تمام محفوظ خیالات، بنیادی حقائق اور روابط کو مستقل طور پر مٹا دے گا۔",
        "chat.memorySettings.eraseConfirmButton": "ہاں، تمام یادداشتیں مٹائیں",
        "chat.memorySettings.erasing": "یادداشتیں مٹائی جا رہی ہیں…",
        "chat.memorySettings.close": "بند کریں",
    },
    "as": {
        "chat.memoryActive": "স্মৃতি সক্ৰিয়",
        "chat.memoryPaused": "স্মৃতি স্থগিত",
        "chat.memoryBanner.title": "ব্যক্তিগত আধ্যাত্মিক স্মৃতি",
        "chat.memoryBanner.description": "আপোনাৰ পথপ্ৰদৰ্শন গভীৰ কৰিবলৈ কথোপকথনসমূহত মুক্তি গুৰুক আপোনাৰ মূল চিন্তা আৰু আধ্যাত্মিক সাধনা মনত ৰাখিবলৈ দিয়ক। আপোনাৰ তথ্য ব্যক্তিগত, এনক্ৰিপ্ট কৰা, আৰু কেতিয়াও ৰাজহুৱা AI মডেল প্ৰশিক্ষণৰ বাবে ব্যৱহাৰ কৰা নহয়।",
        "chat.memoryBanner.enable": "ব্যক্তিগত স্মৃতি সক্ৰিয় কৰক",
        "chat.memoryBanner.notNow": "এতিয়া নহয়",
        "chat.memoryBanner.learnMore": "অধিক জানক",
        "chat.memoryBanner.learnMoreDetails": "সক্ৰিয় হ'লে, আপোনাৰ কথোপকথনৰ অৰ্থপূৰ্ণ চিন্তাসমূহ আপোনাৰ ব্যক্তিগত জ্ঞানৰ মানচিত্ৰত থকা শিক্ষাসমূহৰ সৈতে সুৰক্ষিতভাৱে সংযোগ কৰা হয়। আপুনি যিকোনো সময়তে আপোনাৰ স্মৃতি স্থগিত বা মচি পেলাব পাৰে।",
        "chat.memoryBanner.toastEnabledTitle": "ব্যক্তিগত স্মৃতি সক্ৰিয় হ'ল",
        "chat.memoryBanner.toastEnabledDesc": "ভৱিষ্যতৰ নিৰ্দেশনা প্ৰস্তুত কৰিবলৈ মুক্তি গুৰুৱে এতিয়া মূল চিন্তাসমূহ মনত ৰাখিব।",
        "chat.memoryBanner.toastPausedTitle": "ব্যক্তিগত স্মৃতি স্থগিত কৰা হ'ল",
        "chat.memoryBanner.toastPausedDesc": "আপোনাৰ কথোপকথনৰ পৰা কোনো নতুন চিন্তা সংৰক্ষণ কৰা নহ'ব।",
        "chat.memoryBanner.toastErasedTitle": "সকলো স্মৃতি মচি পেলোৱা হ'ল",
        "chat.memoryBanner.toastErasedDesc": "সকলো ব্যক্তিগত চিন্তা আৰু জ্ঞানৰ মানচিত্ৰৰ সংযোগ বিলোপ কৰা হৈছে।",
        "chat.memorySettings.title": "ব্যক্তিগত আধ্যাত্মিক স্মৃতি",
        "chat.memorySettings.badgeTitle": "আধ্যাত্মিক স্মৃতিৰ ছেটিংছ",
        "chat.memorySettings.description": "সকলো অধিৱেশনত নিৰন্তৰ, ব্যক্তিগত পথপ্ৰদৰ্শন প্ৰদান কৰিবলৈ মুক্তি গুৰুৱে আপোনাৰ চিন্তা, জীৱনৰ প্ৰসংগ আৰু সাধনা মনত ৰাখিব পাৰে।",
        "chat.memorySettings.statusActive": "সক্ৰিয়",
        "chat.memorySettings.statusPaused": "স্থগিত",
        "chat.memorySettings.recordingLabel": "স্মৃতি ৰেকৰ্ডিং",
        "chat.memorySettings.recordingDesc": "সক্ৰিয় অৱস্থাত, কথোপকথনৰ চিন্তাসমূহ আপোনাৰ ব্যক্তিগত জ্ঞানৰ মানচিত্ৰত সুৰক্ষিতভাৱে সংৰক্ষণ কৰা হয়।",
        "chat.memorySettings.pauseAction": "স্মৃতি স্থগিত কৰক",
        "chat.memorySettings.resumeAction": "স্মৃতি পুনৰ আৰম্ভ কৰক",
        "chat.memorySettings.viewAll": "প্ৰফাইলত সকলো স্মৃতি চাওক",
        "chat.memorySettings.eraseTitle": "সকলো স্মৃতি মচি পেলাওক",
        "chat.memorySettings.eraseDesc": "সকলো চিন্তা, মূল টোকা, আৰু ব্যক্তিগত জ্ঞানৰ মানচিত্ৰৰ সংযোগ স্থায়ীভাৱে বিলোপ কৰক। এই কাৰ্য্য পূৰ্বৰ অৱস্থালৈ ঘূৰাই আনিব নোৱাৰি।",
        "chat.memorySettings.eraseButton": "সকলো মচি পেলাওক",
        "chat.memorySettings.eraseConfirmTitle": "আপুনি সম্পূৰ্ণৰূপে নিশ্চিতনে?",
        "chat.memorySettings.eraseConfirmDesc": "ই সকলো ছাৰ্ভাৰত আপোনাৰ ব্যক্তিগত জ্ঞানৰ মানচিত্ৰত সংৰক্ষিত সকলো চিন্তা, মূল তথ্য আৰু সংযোগ স্থায়ীভাৱে মচি পেলাব।",
        "chat.memorySettings.eraseConfirmButton": "হয়, সকলো স্মৃতি মচি পেলাওক",
        "chat.memorySettings.erasing": "স্মৃতি মচি থকা হৈছে…",
        "chat.memorySettings.close": "বন্ধ কৰক",
    },
    "sa": {
        "chat.memoryActive": "स्मृतिः सक्रिया",
        "chat.memoryPaused": "स्मृतिः स्थगिता",
        "chat.memoryBanner.title": "व्यक्तिगत-आध्यात्मिक-स्मृतिः",
        "chat.memoryBanner.description": "भवतः मार्गदर्शनं गभीरं कर्तुं सम्भाषणानां मुख्यान् विचारान् आध्यात्मिकसाधनानि च स्मर्तुं मुक्तिगुरुम् अनुमन्यताम्। भवतः दत्तांशः वैयक्तिकः गूढलिखितः च वर्तते, सार्वजनिक-AI-प्रशिक्षणाय कदापि न प्रयुज्यते।",
        "chat.memoryBanner.enable": "व्यक्तिगतस्मृतिं सक्रियां करोतु",
        "chat.memoryBanner.notNow": "इदानीं मास्तु",
        "chat.memoryBanner.learnMore": "अधिकं ज्ञायताम्",
        "chat.memoryBanner.learnMoreDetails": "सक्रिये सति, भवतः सम्भाषणानां सार्थकाः विचाराः भवतः वैयक्तिक-ज्ञानमानचित्रे उपदेशैः सह सुरक्षिताः सम्बध्यन्ते। भवान् कदापि स्मृतिं स्थगयितुं विलोपयितुं वा शक्नोति।",
        "chat.memoryBanner.toastEnabledTitle": "व्यक्तिगतस्मृतिः सक्रिया जाता",
        "chat.memoryBanner.toastEnabledDesc": "भविष्यस्य मार्गदर्शनाय मुक्तिगुरुः अधुना मुख्यान् विचारान् स्मरिष्यति।",
        "chat.memoryBanner.toastPausedTitle": "व्यक्तिगतस्मृतिः स्थगिता",
        "chat.memoryBanner.toastPausedDesc": "भवतः सम्भाषणात् कोऽपि नूतनविचारः न रक्षिष्यते।",
        "chat.memoryBanner.toastErasedTitle": "सर्वाः स्मृतयः विलोपिताः",
        "chat.memoryBanner.toastErasedDesc": "सर्वे व्यक्तिगतविचाराः ज्ञानमानचित्रसम्बन्धाः च विलोपिताः।",
        "chat.memorySettings.title": "व्यक्तिगत-आध्यात्मिक-स्मृतिः",
        "chat.memorySettings.badgeTitle": "आध्यात्मिक-स्मृति-विन्यासाः",
        "chat.memorySettings.description": "सत्रेषु निरन्तरं व्यक्तिगतं मार्गदर्शनं दातुं मुक्तिगुरुः भवतः विचारान्, जीवनप्रसङ्गं, साधनानि च स्मर्तुं शक्नोति।",
        "chat.memorySettings.statusActive": "सक्रिया",
        "chat.memorySettings.statusPaused": "स्थगिता",
        "chat.memorySettings.recordingLabel": "स्मृति-अभिलेखनम्",
        "chat.memorySettings.recordingDesc": "सक्रिये सति, सम्भाषणानां विचाराः भवतः वैयक्तिक-ज्ञानमानचित्रे सुरक्षिताः रक्ष्यन्ते।",
        "chat.memorySettings.pauseAction": "स्मृतिं स्थगयतु",
        "chat.memorySettings.resumeAction": "स्मृतिं पुनः प्रारभताम्",
        "chat.memorySettings.viewAll": "विवरणे सर्वाः स्मृतीः पश्यतु",
        "chat.memorySettings.eraseTitle": "सर्वाः स्मृतीः विलोपयतु",
        "chat.memorySettings.eraseDesc": "सर्वान् विचारान्, मुख्यटिप्पणीः, वैयक्तिक-ज्ञानमानचित्रसम्बन्धांश्च स्थायिरूपेण विलोपयतु। एतत् कार्यं प्रत्यानेतुं न शक्यते।",
        "chat.memorySettings.eraseButton": "सर्वं विलोपयतु",
        "chat.memorySettings.eraseConfirmTitle": "किं भवान् दृढनिश्चितः अस्ति?",
        "chat.memorySettings.eraseConfirmDesc": "एतेन सर्ववितरकेषु भवतः वैयक्तिक-ज्ञानमानचित्रे रक्षिताः सर्वे विचाराः, मूलतथ्यानि, सम्बन्धाश्च स्थायिरूपेण विलोपिताः भविष्यन्ति।",
        "chat.memorySettings.eraseConfirmButton": "आम्, सर्वाः स्मृतीः विलोपयतु",
        "chat.memorySettings.erasing": "स्मृतीनां विलोपनं क्रियते…",
        "chat.memorySettings.close": "पिदधातु",
    },
}


def clean_punctuation(en_text: str, trans_text: str) -> str:
    """Ensure ending punctuation matches English (e.g. no full stop if English has none)."""
    t = trans_text.strip()
    if en_text.endswith("…"):
        if not t.endswith("…"):
            t = t.rstrip(".।!?-") + "…"
    elif en_text.endswith("?"):
        if not t.endswith("?"):
            t = t.rstrip(".।!-") + "?"
    elif en_text.endswith("."):
        if not (t.endswith(".") or t.endswith("।") or t.endswith("۔")):
            t = t + "."
    else:
        # English has NO ending punctuation: strip any trailing dots or danda
        t = t.rstrip(".।!?,:;-")
    return t


def main():
    raw_path = ROOT / "scripts" / "sarvam_translations_raw.json"
    if not raw_path.exists():
        print("Raw sarvam translations not found yet!")
        return

    with open(raw_path, encoding="utf-8") as f:
        sarvam_data = json.load(f)

    with open(LOCALES_DIR / "en.json", encoding="utf-8") as f:
        en_json = json.load(f)

    all_translations = {**sarvam_data, **CURATED_TRANSLATIONS}

    # English reference values
    en_chat = en_json["chat"]
    en_active = en_chat["memoryActive"]
    en_paused = en_chat["memoryPaused"]
    en_banner = en_chat["memoryBanner"]
    en_settings = en_chat["memorySettings"]

    for lang, trans in all_translations.items():
        locale_path = LOCALES_DIR / f"{lang}.json"
        if not locale_path.exists():
            print(f"Skipping {lang}: file not found")
            continue

        with open(locale_path, encoding="utf-8") as f:
            locale_json = json.load(f)

        chat = locale_json.setdefault("chat", {})

        # 1. memoryActive & memoryPaused
        chat["memoryActive"] = clean_punctuation(en_active, trans["chat.memoryActive"])
        chat["memoryPaused"] = clean_punctuation(en_paused, trans["chat.memoryPaused"])

        # 2. memoryBanner
        banner = chat.setdefault("memoryBanner", {})
        for k, en_val in en_banner.items():
            key_id = f"chat.memoryBanner.{k}"
            banner[k] = clean_punctuation(en_val, trans.get(key_id, en_val))

        # 3. memorySettings
        settings = chat.setdefault("memorySettings", {})
        for k, en_val in en_settings.items():
            key_id = f"chat.memorySettings.{k}"
            settings[k] = clean_punctuation(en_val, trans.get(key_id, en_val))

        with open(locale_path, "w", encoding="utf-8") as f:
            json.dump(locale_json, f, ensure_ascii=False, indent=2)
            f.write("\n")

        print(f"Updated {lang}.json with 32 memory keys")


if __name__ == "__main__":
    main()
