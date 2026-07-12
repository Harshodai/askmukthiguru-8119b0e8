import { useTranslation } from 'react-i18next';
import { X, Link as LinkIcon, ExternalLink, Play, Youtube } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

export interface Citation {
  url: string;
  title?: string;
  quote?: string;
  channel_name?: string;
}

interface CitationPanelProps {
  isOpen: boolean;
  onClose: () => void;
  citations: Citation[];
}

export function CitationPanel({ isOpen, onClose, citations }: CitationPanelProps) {
  const { t } = useTranslation();

  const getDomain = (url: string): string => {
    try {
      return new URL(url).hostname.replace(/^www\./, "");
    } catch {
      return url;
    }
  };

  const getYouTubeId = (url: string): string | null => {
    try {
      if (url.includes("youtu.be/")) return url.split("youtu.be/")[1]?.split("?")[0];
      if (url.includes("v=")) return url.split("v=")[1]?.split("&")[0];
      return null;
    } catch {
      return null;
    }
  };

  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full sm:max-w-lg p-0">
        <SheetHeader className="px-5 pt-5 pb-3 border-b">
          <div className="flex items-center justify-between">
            <SheetTitle className="flex items-center gap-2">
              <LinkIcon className="w-5 h-5 text-ojas" />
              {t('chat.sourcesReferences')}
            </SheetTitle>
          </div>
        </SheetHeader>
        <ScrollArea className="h-[calc(100vh-80px)] p-5">
          {citations.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <LinkIcon className="w-10 h-10 mx-auto mb-3 text-muted-foreground/30" />
              <p className="text-sm">{t('chat.noCitations')}</p>
            </div>
          ) : (
            <div className="space-y-4">
              {citations.map((c, idx) => {
                const ytId = getYouTubeId(c.url);
                return (
                  <div key={idx} className="border rounded-lg p-4 hover:bg-muted/30 transition-colors">
                    <div className="flex items-start gap-3">
                      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-ojas/10 text-ojas text-xs font-medium flex items-center justify-center">
                        {idx + 1}
                      </span>
                      <div className="flex-1 min-w-0">
                        <a
                          href={c.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm font-medium text-ojas hover:underline flex items-center gap-1"
                        >
                          {c.title || getDomain(c.url)}
                          <ExternalLink className="w-3 h-3" />
                        </a>
                        <p className="text-xs text-muted-foreground mt-0.5">{getDomain(c.url)}</p>
                        {c.quote && (
                          <blockquote className="mt-2 text-sm text-foreground/80 border-l-2 border-ojas/30 pl-3 italic">
                            {c.quote}
                          </blockquote>
                        )}
                        {c.channel_name && (
                          <p className="text-xs text-muted-foreground mt-1">{t('chat.channelLabel', { channel: c.channel_name })}</p>
                        )}
                        {ytId && (
                          <div className="mt-3">
                            <a
                              href={c.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="block rounded-lg overflow-hidden border group transition-colors"
                            >
                              <div className="relative aspect-video bg-black/10">
                                <img
                                  src={`https://img.youtube.com/vi/${ytId}/hqdefault.jpg`}
                                  alt="YouTube thumbnail"
                                  className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity"
                                  loading="lazy"
                                />
                                <div className="absolute inset-0 flex items-center justify-center bg-black/30">
                                  <div className="w-12 h-12 rounded-full bg-white/90 flex items-center justify-center shadow-lg group-hover:scale-110 transition-transform">
                                    <Play className="w-5 h-5 text-red-600 fill-red-600 ml-0.5" />
                                  </div>
                                </div>
                              </div>
                              <div className="p-2 bg-background border-t">
                                <p className="text-xs font-medium text-ojas flex items-center gap-1">
                                  <Youtube className="w-3 h-3 text-red-500" />
                                  Watch on YouTube
                                </p>
                              </div>
                            </a>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
