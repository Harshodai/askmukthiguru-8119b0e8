import { useState, useEffect, useRef } from 'react';
import { Upload, Trash2, Eye, Image as ImageIcon, History } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { supabase } from '@/integrations/supabase/client';
import type { DailyTeachingData } from '@/components/chat/DailyTeaching';

interface TeachingHistoryItem {
  id: string;
  imageUrl: string;
  caption?: string;
  createdAt: string;
}

const DailyTeachingPage = () => {
  const [caption, setCaption] = useState('');
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [currentTeaching, setCurrentTeaching] = useState<DailyTeachingData | null>(null);
  const [published, setPublished] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<TeachingHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchCurrentTeaching();
    fetchHistory();
  }, []);

  const fetchCurrentTeaching = async () => {
    const { data } = await supabase
      .from('daily_teachings')
      .select('id, image_url, caption')
      .order('created_at', { ascending: false })
      .limit(1)
      .maybeSingle();

    if (data) {
      setCurrentTeaching({
        id: data.id,
        imageUrl: data.image_url,
        caption: data.caption ?? undefined,
      });
    } else {
      setCurrentTeaching(null);
    }
  };

  const fetchHistory = async () => {
    setHistoryLoading(true);
    const { data, error } = await supabase
      .from('daily_teachings')
      .select('id, image_url, caption, created_at')
      .order('created_at', { ascending: false });

    if (error) {
      console.error('Failed to fetch history:', error);
      setHistory([]);
    } else {
      setHistory(
        (data || []).map((item) => ({
          id: item.id,
          imageUrl: item.image_url,
          caption: item.caption ?? undefined,
          createdAt: item.created_at ?? new Date().toISOString(),
        }))
      );
    }
    setHistoryLoading(false);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !file.type.startsWith('image/') || file.size > 5 * 1024 * 1024) return;

    setImageFile(file);
    const reader = new FileReader();
    reader.onload = (ev) => setImagePreview(ev.target?.result as string);
    reader.readAsDataURL(file);
  };

  const handlePublish = async () => {
    if (!imageFile) return;
    setLoading(true);
    setError(null);

    try {
      const {
        data: { session },
      } = await supabase.auth.getSession();

      const fileName = `teaching-${Date.now()}.${imageFile.name.split('.').pop()}`;
      const { error: uploadError } = await supabase.storage
        .from('daily-teachings')
        .upload(fileName, imageFile, { upsert: true });

      if (uploadError) throw new Error(`Upload failed: ${uploadError.message}`);

      const { data: urlData } = supabase.storage
        .from('daily-teachings')
        .getPublicUrl(fileName);

      const { error: insertError } = await supabase.from('daily_teachings').insert({
        image_url: urlData.publicUrl,
        caption: caption.trim() || null,
        created_by: session?.user?.id ?? null,
      });

      if (insertError) throw new Error(`Database error: ${insertError.message}`);

      setPublished(true);
      setTimeout(() => setPublished(false), 3000);

      // Reset form
      setCaption('');
      setImageFile(null);
      setImagePreview(null);

      await fetchCurrentTeaching();
      await fetchHistory();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setError(msg);
      console.error('Failed to publish teaching:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleClear = async () => {
    if (!currentTeaching) return;
    const { error } = await supabase
      .from('daily_teachings')
      .delete()
      .eq('id', currentTeaching.id);
    if (error) {
      setError(`Delete failed: ${error.message}`);
      return;
    }
    setCurrentTeaching(null);
    setImagePreview(null);
    setCaption('');
    setError(null);
    await fetchHistory();
  };

  const handleDeleteHistoryItem = async (id: string) => {
    const { error } = await supabase.from('daily_teachings').delete().eq('id', id);
    if (error) {
      setError(`Delete failed: ${error.message}`);
      return;
    }
    // If we deleted the current one, refresh current too
    if (currentTeaching?.id === id) {
      setCurrentTeaching(null);
    }
    await fetchHistory();
    await fetchCurrentTeaching();
  };

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Daily Teaching</h1>
        <p className="text-muted-foreground mt-1">
          Upload an image with a caption that all users will see today in the chat. The teaching
          automatically expires after 24 hours.
        </p>
      </div>

      <Tabs defaultValue="active">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="active">Active Teaching</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>

        <TabsContent value="active" className="space-y-6 mt-6">
          {/* Current Status */}
          {currentTeaching ? (
            <Card className="border-ojas/30 bg-ojas/5">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Eye className="w-4 h-4 text-ojas" />
                    Active Teaching
                  </CardTitle>
                  <Badge variant="outline" className="border-ojas/40 text-ojas">
                    Live now
                  </Badge>
                </div>
                <CardDescription>
                  Automatically expires 24 hours after publishing.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="rounded-lg overflow-hidden border border-border/50 aspect-[16/7]">
                  <img
                    src={currentTeaching.imageUrl}
                    alt="Current teaching"
                    className="w-full h-full object-cover"
                  />
                </div>
                {currentTeaching.caption && (
                  <p className="text-sm text-foreground">{currentTeaching.caption}</p>
                )}
                <Button variant="destructive" size="sm" onClick={handleClear}>
                  <Trash2 className="w-3.5 h-3.5 mr-1.5" />
                  Remove Teaching
                </Button>
              </CardContent>
            </Card>
          ) : (
            <Card className="border-dashed border-border/40">
              <CardContent className="py-8 flex flex-col items-center gap-2 text-muted-foreground">
                <Eye className="w-8 h-8 opacity-50" />
                <p className="text-sm">No active teaching. Upload one below.</p>
              </CardContent>
            </Card>
          )}

          {/* Upload New */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                {currentTeaching ? 'Replace Teaching' : 'Publish New Teaching'}
              </CardTitle>
              <CardDescription>
                Upload a photo (max 5MB). It will be shown to all users in the chat.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  onChange={handleFileChange}
                  className="hidden"
                />
                {imagePreview ? (
                  <div className="space-y-2">
                    <div className="rounded-lg overflow-hidden border border-border/50 aspect-[16/7]">
                      <img
                        src={imagePreview}
                        alt="Preview"
                        className="w-full h-full object-cover"
                      />
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => fileInputRef.current?.click()}
                    >
                      Change image
                    </Button>
                  </div>
                ) : (
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="w-full border-2 border-dashed border-border/60 rounded-xl p-8 flex flex-col items-center gap-2 hover:border-ojas/40 hover:bg-ojas/5 transition-colors"
                  >
                    <ImageIcon className="w-8 h-8 text-muted-foreground" />
                    <span className="text-sm text-muted-foreground">Click to upload an image</span>
                    <span className="text-[11px] text-muted-foreground/60">
                      JPG, PNG, WebP — max 5MB
                    </span>
                  </button>
                )}
              </div>

              <div>
                <label className="text-sm font-medium text-foreground mb-1.5 block">
                  Caption (optional)
                </label>
                <Textarea
                  value={caption}
                  onChange={(e) => setCaption(e.target.value)}
                  placeholder="A message of wisdom for today…"
                  rows={2}
                  maxLength={200}
                  className="resize-none"
                />
                <p className="text-[11px] text-muted-foreground mt-1">
                  {caption.length}/200 characters
                </p>
              </div>

              <Button
                onClick={handlePublish}
                disabled={!imageFile || loading}
                className="w-full bg-ojas hover:bg-ojas/90 text-primary-foreground"
              >
                <Upload className="w-4 h-4 mr-2" />
                {published
                  ? '✓ Published!'
                  : loading
                    ? 'Uploading…'
                    : 'Publish Teaching'}
              </Button>

              {error && (
                <p className="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">
                  {error}
                </p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="history" className="mt-6">
          {historyLoading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
              Loading history…
            </div>
          ) : history.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground text-sm flex flex-col items-center gap-2">
              <History className="w-8 h-8 opacity-50" />
              <p>No past teachings found.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {history.map((item) => (
                <Card key={item.id} className="overflow-hidden">
                  <CardContent className="p-3 flex items-center gap-4">
                    <div className="w-20 h-14 rounded-md overflow-hidden flex-shrink-0 border border-border/50">
                      <img
                        src={item.imageUrl}
                        alt="Teaching thumbnail"
                        className="w-full h-full object-cover"
                        loading="lazy"
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      {item.caption ? (
                        <p className="text-sm font-medium text-foreground truncate">
                          {item.caption}
                        </p>
                      ) : (
                        <p className="text-sm text-muted-foreground italic">No caption</p>
                      )}
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {new Date(item.createdAt).toLocaleDateString(undefined, {
                          year: 'numeric',
                          month: 'short',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="text-destructive hover:text-destructive flex-shrink-0"
                      onClick={() => handleDeleteHistoryItem(item.id)}
                      aria-label="Delete"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default DailyTeachingPage;
