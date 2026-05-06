import { useState, useEffect, useRef } from 'react';
import { Upload, Trash2, Eye, Image as ImageIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { supabase } from '@/integrations/supabase/client';
import type { DailyTeachingData } from '@/components/chat/DailyTeaching';

const DailyTeachingPage = () => {
  const [caption, setCaption] = useState('');
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [currentTeaching, setCurrentTeaching] = useState<DailyTeachingData | null>(null);
  const [published, setPublished] = useState(false);
  const [loading, setLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchCurrentTeaching();
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

    try {
      // Get current admin user for audit trail
      const { data: { session } } = await supabase.auth.getSession();

      // Upload image to storage
      const fileName = `teaching-${Date.now()}.${imageFile.name.split('.').pop()}`;
      const { error: uploadError } = await supabase.storage
        .from('daily-teachings')
        .upload(fileName, imageFile, { upsert: true });

      if (uploadError) throw uploadError;

      // Get public URL
      const { data: urlData } = supabase.storage
        .from('daily-teachings')
        .getPublicUrl(fileName);

      // Insert into database (TTL is handled by default expires_at = now() + 24h)
      const { error: insertError } = await supabase
        .from('daily_teachings')
        .insert({
          image_url: urlData.publicUrl,
          caption: caption.trim() || null,
          created_by: session?.user?.id ?? null,
        });

      if (insertError) throw insertError;

      setPublished(true);
      setTimeout(() => setPublished(false), 3000);
      await fetchCurrentTeaching();
    } catch (err) {
      console.error('Failed to publish teaching:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleClear = async () => {
    if (!currentTeaching) return;
    await supabase.from('daily_teachings').delete().eq('id', currentTeaching.id);
    setCurrentTeaching(null);
    setImagePreview(null);
    setCaption('');
  };

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Daily Teaching</h1>
        <p className="text-muted-foreground mt-1">
          Upload an image with a caption that all users will see today in the chat.
          The teaching automatically expires after 24 hours.
        </p>
      </div>

      {/* Current Status */}
      {currentTeaching && (
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
                  <img src={imagePreview} alt="Preview" className="w-full h-full object-cover" />
                </div>
                <Button variant="outline" size="sm" onClick={() => fileInputRef.current?.click()}>
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
                <span className="text-[11px] text-muted-foreground/60">JPG, PNG, WebP — max 5MB</span>
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
            <p className="text-[11px] text-muted-foreground mt-1">{caption.length}/200 characters</p>
          </div>

          <Button
            onClick={handlePublish}
            disabled={!imageFile || loading}
            className="w-full bg-ojas hover:bg-ojas/90 text-primary-foreground"
          >
            <Upload className="w-4 h-4 mr-2" />
            {published ? '✓ Published!' : loading ? 'Uploading…' : 'Publish Teaching'}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};

export default DailyTeachingPage;
