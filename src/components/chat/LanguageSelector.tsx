import { useState } from 'react';
import { Globe, Mic, Volume2 } from 'lucide-react';
import { setLanguage } from '@/lib/aiService';

const languages = [
  { code: 'en', name: 'English', native: 'English' },
  { code: 'hi', name: 'Hindi', native: 'हिंदी' },
  { code: 'te', name: 'Telugu', native: 'తెలుగు' },
  { code: 'ta', name: 'Tamil', native: 'தமிழ்' },
  { code: 'kn', name: 'Kannada', native: 'ಕನ್ನಡ' },
  { code: 'ml', name: 'Malayalam', native: 'മലയാളം' },
];

interface LanguageSelectorProps {
  onVoiceToggle?: () => void;
  voiceEnabled?: boolean;
}

export const LanguageSelector = ({ onVoiceToggle, voiceEnabled }: LanguageSelectorProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [selectedLanguage, setSelectedLanguage] = useState('en');

  const handleLanguageChange = (code: string) => {
    setSelectedLanguage(code);
    setLanguage(code);
    setIsOpen(false);
  };

  const currentLang = languages.find((l) => l.code === selectedLanguage);

  return (
    <div className="flex items-center gap-2">
      {/* Language Dropdown */}
      <div className="relative">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-muted/50 hover:bg-muted transition-colors text-xs"
        >
          <Globe className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="text-tejas">{currentLang?.native || 'EN'}</span>
        </button>

        {isOpen && (
          <>
            <div
              className="fixed inset-0 z-40"
              onClick={() => setIsOpen(false)}
            />
            <div className="absolute bottom-full left-0 mb-2 w-40 bg-card border border-border rounded-lg shadow-lg z-50 overflow-hidden">
              {languages.map((lang) => (
                <button
                  key={lang.code}
                  onClick={() => handleLanguageChange(lang.code)}
                  className={`w-full px-3 py-2 text-left text-sm hover:bg-muted/50 transition-colors ${
                    selectedLanguage === lang.code ? 'bg-ojas/10 text-ojas' : 'text-tejas'
                  }`}
                >
                  <span className="font-medium">{lang.native}</span>
                  <span className="text-muted-foreground ml-2 text-xs">{lang.name}</span>
                </button>
              ))}
              <div className="px-3 py-2 text-xs text-muted-foreground/60 border-t border-border/50">
                Powered by Bhashini (Coming Soon)
              </div>
            </div>
          </>
        )}
      </div>

      {/* Voice Mode Toggle */}
      <button
        onClick={onVoiceToggle}
        className={`p-2 rounded-full transition-colors ${
          voiceEnabled
            ? 'bg-ojas/20 text-ojas'
            : 'bg-muted/50 text-muted-foreground hover:bg-muted'
        }`}
        title={voiceEnabled ? 'Voice mode on' : 'Enable voice mode'}
      >
        {voiceEnabled ? (
          <Volume2 className="w-4 h-4" />
        ) : (
          <Mic className="w-4 h-4" />
        )}
      </button>
    </div>
  );
};
