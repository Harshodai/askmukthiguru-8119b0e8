import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Sparkles, Brain, Check, RefreshCw } from 'lucide-react';
import { supabase } from '@/integrations/supabase/client';

interface Flashcard {
  id: string;
  question: string;
  answer: string;
  easiness_factor: number;
  interval_days: number;
  repetitions: number;
}

export const FlashcardPractice = () => {
  const [cards, setCards] = useState<Flashcard[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [showAnswer, setShowAnswer] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [fetchState, setFetchState] = useState<'initial' | 'success' | 'error'>('initial');
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchDueCards = async () => {
    setLoading(true);
    setFetchState('initial');
    setFetchError(null);
    try {
      // Get auth session to call endpoint
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;

      if (!token) {
        setCards([]);
        setFetchState('error');
        setFetchError('Sign in to start your active recall practice.');
        setLoading(false);
        return;
      }

      const response = await fetch('/api/srs/due?limit=10', {
        headers: {
          'Authorization': `Bearer ${token}`,
        }
      });
      if (response.ok) {
        const data = await response.json();
        setCards(data);
        setCurrentIndex(0);
        setShowAnswer(false);
        setFetchState('success');
      } else {
        setCards([]);
        setFetchState('error');
        setFetchError(response.status === 401
          ? 'Your session expired. Please sign in again.'
          : 'Could not load your reflection cards right now.');
      }
    } catch (error) {
      console.error('Failed to load due flashcards:', error);
      setCards([]);
      setFetchState('error');
      setFetchError('Could not reach the server. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDueCards();
  }, []);

  const handleRate = async (rating: number) => {
    if (cards.length === 0 || submitting) return;
    setSubmitting(true);
    const card = cards[currentIndex];
    
    try {
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;

      const response = await fetch('/api/srs/review', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          card_id: card.id,
          rating: rating
        })
      });

      if (response.ok) {
        setError(null);
        if (currentIndex < cards.length - 1) {
          setCurrentIndex((prev) => prev + 1);
          setShowAnswer(false);
        } else {
          fetchDueCards();
        }
      } else {
        const errData = await response.json().catch(() => ({}));
        setError(errData.message || "Failed to submit review");
      }
    } catch (error) {
      setError("Network error — could not submit review");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <Card className="border-ojas/20 bg-zinc-950/40 backdrop-blur-sm">
        <CardContent className="py-10 text-center text-sm text-muted-foreground animate-pulse">
          Recalling active reflection cards…
        </CardContent>
      </Card>
    );
  }

  if (fetchState !== 'success' || cards.length === 0) {
    return (
      <Card className="border-ojas/20 bg-zinc-950/30">
        <CardContent className="py-8 text-center space-y-3">
          {fetchState === 'error' ? (
            <>
              <Sparkles className="w-8 h-8 text-ojas/80 mx-auto" />
              <h3 className="text-sm font-medium text-foreground">Practice unavailable</h3>
              <p className="text-xs text-muted-foreground max-w-xs mx-auto">
                {fetchError ?? 'Could not load your reflection cards.'}
              </p>
              <Button variant="outline" size="sm" onClick={fetchDueCards} className="mt-2 text-xs">
                <RefreshCw className="w-3 h-3 mr-1.5" /> Try again
              </Button>
            </>
          ) : (
            <>
              <Brain className="w-8 h-8 text-emerald-500/80 mx-auto" />
              <h3 className="text-sm font-medium text-foreground">All caught up!</h3>
              <p className="text-xs text-muted-foreground max-w-xs mx-auto">
                You have no active recall cards due for review today. Check back as you add more notebook insights!
              </p>
              <Button variant="outline" size="sm" onClick={fetchDueCards} className="mt-2 text-xs">
                <RefreshCw className="w-3 h-3 mr-1.5" /> Refresh
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    );
  }

  const currentCard = cards[currentIndex];

  return (
    <Card className="border-ojas/20 bg-gradient-to-b from-zinc-950/60 to-zinc-950/20 backdrop-blur-md shadow-xl transition-all duration-300">
      <CardHeader className="pb-2 flex flex-row items-center justify-between">
        <CardTitle className="text-xs font-serif uppercase tracking-widest text-ojas flex items-center gap-1.5">
          <Brain className="w-4 h-4 text-emerald-500" /> Active Recall Practice
        </CardTitle>
        <span className="text-[10px] font-mono text-muted-foreground">
          Card {currentIndex + 1} of {cards.length}
        </span>
      </CardHeader>
      
      <CardContent className="space-y-6">
        {/* Flashcard container */}
        <div className="min-h-[140px] rounded-lg bg-zinc-900/60 border border-zinc-800/80 p-5 flex flex-col justify-between transition-all duration-300 hover:border-zinc-700/50">
          <div className="space-y-3">
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">Question</span>
            <p className="font-serif text-base leading-relaxed text-foreground/95">
              {currentCard.question}
            </p>
          </div>

          {showAnswer && (
            <div className="mt-5 pt-4 border-t border-zinc-800/80 space-y-2 animate-in fade-in slide-in-from-bottom-2 duration-300">
              <span className="text-[10px] text-emerald-500 uppercase tracking-wider font-semibold">Answer</span>
              <p className="text-sm leading-relaxed text-zinc-300">
                {currentCard.answer}
              </p>
            </div>
          )}
        </div>

        {/* Buttons layout */}
        <div className="flex flex-col gap-3">
          {!showAnswer ? (
            <Button 
              onClick={() => setShowAnswer(true)} 
              className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-medium shadow-lg shadow-emerald-950/20"
            >
              Reveal Answer
            </Button>
          ) : (
            <div className="space-y-3">
              {error && <p className="text-red-400 text-xs text-center mt-2">{error}</p>}
              <span className="text-[10px] text-zinc-400 font-medium block text-center">
                Rate your recollection difficulty to schedule the next review:
              </span>
              <div className="grid grid-cols-6 gap-1.5">
                {[0, 1, 2, 3, 4, 5].map((rating) => {
                  const labels = ['Forgot', 'Hard', 'Decent', 'Good', 'Easy', 'Perfect'];
                  return (
                    <button
                      key={rating}
                      disabled={submitting}
                      onClick={() => handleRate(rating)}
                      className="group flex flex-col items-center justify-center py-2.5 px-1 rounded-md bg-zinc-900 border border-zinc-800/80 hover:bg-emerald-950/20 hover:border-emerald-600/40 text-xs font-semibold text-zinc-300 transition-all active:scale-95 disabled:opacity-50"
                    >
                      <span className="text-sm text-foreground group-hover:text-emerald-400 font-mono mb-0.5">
                        {rating}
                      </span>
                      <span className="text-[8px] text-zinc-500 group-hover:text-zinc-400 truncate max-w-full">
                        {labels[rating]}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};
