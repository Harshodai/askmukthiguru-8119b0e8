import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Sparkles, Trash2, Menu, Wifi, WifiOff } from 'lucide-react';
import { checkConnection } from '@/lib/aiService';
import gurusPhoto from '@/assets/gurus-photo.jpg';

interface ChatHeaderProps {
  onClearChat: () => void;
  onOpenMobileMenu?: () => void;
}

export const ChatHeader = ({ onClearChat, onOpenMobileMenu }: ChatHeaderProps) => {
  const [connectionStatus, setConnectionStatus] = useState<{ connected: boolean; mode: string }>({
    connected: true,
    mode: 'Offline Mode',
  });

  useEffect(() => {
    const checkStatus = async () => {
      const status = await checkConnection();
      setConnectionStatus(status);
    };
    
    checkStatus();
    // Check connection every 30 seconds
    const interval = setInterval(checkStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="relative z-20 glass-card mx-4 mt-4 px-4 py-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {/* Back button - hidden on mobile when menu is available */}
          <Link 
            to="/" 
            className="p-2 rounded-full hover:bg-muted/50 transition-colors hidden sm:flex"
          >
            <ArrowLeft className="w-5 h-5 text-tejas" />
          </Link>
          
          {/* Mobile menu button */}
          {onOpenMobileMenu && (
            <button
              onClick={onOpenMobileMenu}
              className="p-2 rounded-full hover:bg-muted/50 transition-colors sm:hidden"
            >
              <Menu className="w-5 h-5 text-tejas" />
            </button>
          )}

          {/* Guru Avatar and Info */}
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-full overflow-hidden ring-2 ring-ojas/30">
              <img
                src={gurusPhoto}
                alt="Sri Preethaji & Sri Krishnaji"
                className="w-full h-full object-cover"
              />
            </div>
            <div>
              <h1 className="font-semibold text-tejas text-sm sm:text-base">
                Sri Preethaji & Sri Krishnaji
              </h1>
              <div className="flex items-center gap-1.5">
              {connectionStatus.connected ? (
                  <Wifi className="w-3 h-3 text-accent" />
                ) : (
                  <WifiOff className="w-3 h-3 text-muted-foreground" />
                )}
                <p className="text-xs text-muted-foreground">{connectionStatus.mode}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={onClearChat}
            className="p-2 rounded-full hover:bg-destructive/20 transition-colors group"
            title="Clear chat history"
          >
            <Trash2 className="w-5 h-5 text-muted-foreground group-hover:text-destructive transition-colors" />
          </button>
        </div>
      </div>
    </header>
  );
};
