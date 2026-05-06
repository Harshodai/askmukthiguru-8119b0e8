import { useState, useEffect, useRef } from 'react';
import { Upload, Trash2, Eye, Image as ImageIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  setDailyTeaching,
  getDailyTeaching,
  clearDailyTeaching,
  type DailyTeachingData,
} from '@/components/chat/DailyTeaching';

const DailyTeachingPage = () => {
  const [caption, setCaption] = useState('');
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [currentTeaching, setCurrentTeaching] = useState<DailyTeachingData | null>(null);
  const [published, setPublished] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setCurrentTeaching(getDailyTeaching());
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (!file.type.startsWith('image/')) {
      return;
    }

    // Max 5MB for localStorage storage
    if (file.size > 5 * 1024 * 1024) {
      return;
    }

    const reader = new FileReader();
    reader.onload = (ev) => {
      const dataUrl = ev.target?.result as string;
      setImagePreview(dataUrl);
    };
    reader.readAsDataURL(file);
  };

  const handlePublish = () => {
    if (!imagePreview) return;

    const today = new Date().toISOString().slice(0, 10);
    const teaching: DailyTeachingData = {
      id: `teaching-${today}`,
      imageUrl: imagePreview,
      caption: caption.trim() || undefined,
      date: today,
    };

    setDailyTeaching(teaching);
    setCurrentTeaching(teaching);
    setPublished(true);
    setTimeout(() => setPublished(false), 3000);
  };

  const handleClear = () => {
    clearDailyTeaching();
    setCurrentTeaching(null);
    setImagePreview(null);
    setCaption('');
  };

  const today = new Date().toISOString().slice(0, 10);
  const isActive = currentTeaching?.date === today;

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
      {isActive && currentTeaching && (
        <Card className="border-ojas/30 bg-ojas/5">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <Eye className="w-4 h-4 text-ojas" />
                Active Teaching
              </CardTitle>
              <Badge variant="outline" className="border-ojas/40 text-ojas">
                Live today
              </Badge>
            </div>
            <CardDescription>
              Published for {currentTeaching.date}. Expires at midnight.
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
            {isActive ? 'Replace Teaching' : 'Publish New Teaching'}
          </CardTitle>
          <CardDescription>
            Upload a photo (max 5MB). It will be shown to all users in the chat after they complete their daily practice check-in.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* File Upload */}
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
                <span className="text-sm text-muted-foreground">
                  Click to upload an image
                </span>
                <span className="text-[11px] text-muted-foreground/60">
                  JPG, PNG, WebP — max 5MB
                </span>
              </button>
            )}
          </div>

          {/* Caption */}
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

          {/* Publish */}
          <Button
            onClick={handlePublish}
            disabled={!imagePreview}
            className="w-full bg-ojas hover:bg-ojas/90 text-primary-foreground"
          >
            <Upload className="w-4 h-4 mr-2" />
            {published ? '✓ Published!' : 'Publish Teaching'}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};

export default DailyTeachingPage;