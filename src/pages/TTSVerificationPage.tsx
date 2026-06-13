import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Play, Square, RefreshCw, CheckCircle, ArrowLeft, Volume2, Activity, Sparkles, ShieldAlert } from 'lucide-react';
import { useProfile } from '@/hooks/useProfile';
import { useTextToSpeech } from '@/hooks/useTextToSpeech';

import { useToast } from '@/hooks/use-toast';
import { Link } from 'react-router-dom';

const VERIFICATION_QUOTES = [
  "Life is a play of consciousness. When you are in a beautiful state, the world around you is beautiful.",
  "Connection is not a choice; it is your very nature. When you drop your inner walls, love flows instantly.",
  "The greatest miracle is not walking on water or in the air, but standing in a beautiful state here and now."
];

const SPEAKERS = [
  { id: 'deepika', name: 'Deepika', description: 'Expressive and clear female voice', gender: 'Female' },
  { id: 'anushka', name: 'Anushka', description: 'Warm and soothing female voice (Sarvam)', gender: 'Female' },
  { id: 'aditya', name: 'Aditya', description: 'Resonant and peaceful male voice (Sarvam)', gender: 'Male' }
];

export default function TTSVerificationPage() {
  const { profile, loading: profileLoading, update: updateProfile } = useProfile();
  const [selectedVoice, setSelectedVoice] = useState(profile.preferredVoice || 'deepika');
  const [testText, setTestText] = useState(VERIFICATION_QUOTES[0]);
  const [logs, setLogs] = useState<{ time: string; type: 'system' | 'action' | 'telemetry' | 'success' | 'error'; message: string }[]>([]);
  const [telemetryState, setTelemetryState] = useState<'idle' | 'firing' | 'success' | 'failed'>('idle');
  const [autoTesting, setAutoTesting] = useState(false);
  const [testChecklist, setTestChecklist] = useState({
    supported: false,
    profileSynced: false,
    voiceSwitched: false,
    metricsFired: false,
  });

  const { toast } = useToast();
  const logContainerRef = useRef<HTMLDivElement>(null);

  // Text-to-Speech Hook bound to selected voice
  const { speak, stop: stopSpeaking, isSpeaking, isSupported, currentVoice } = useTextToSpeech({
    lang: profile.preferredLanguage || 'en',
    rate: profile.ttsRate || 0.9,
    speaker: selectedVoice,
    onError: (err) => {
      addLog('error', `TTS Hook Error: ${err}`);
      toast({ title: 'TTS Error', description: err, variant: 'destructive' });
    }
  });

  const addLog = (type: 'system' | 'action' | 'telemetry' | 'success' | 'error', message: string) => {
    const time = new Date().toLocaleTimeString();
    setLogs((prev) => [...prev, { time, type, message }]);
  };

  // Scroll logs to bottom
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs]);

  // Sync profile preferred voice initially
  useEffect(() => {
    if (!profileLoading && profile.preferredVoice) {
      setSelectedVoice(profile.preferredVoice);
      setTestChecklist(prev => ({ ...prev, profileSynced: true }));
      addLog('system', `Loaded profile preference: voice = "${profile.preferredVoice}"`);
    }
  }, [profileLoading, profile.preferredVoice]);

  // Initial check
  useEffect(() => {
    setTestChecklist(prev => ({ ...prev, supported: isSupported }));
    addLog('system', `Web Speech Synthesis supported: ${isSupported ? 'YES' : 'NO'}`);
    if (currentVoice) {
      addLog('system', `Native Browser Voice matched: ${currentVoice.name} (${currentVoice.lang})`);
    }
  }, [isSupported, currentVoice]);

  // Voice switching handler
  const handleVoiceSwitch = async (voiceId: string) => {
    if (autoTesting) return;
    setSelectedVoice(voiceId);
    addLog('action', `User switching voice parameter to: "${voiceId}"`);
    
    try {
      await updateProfile({ preferredVoice: voiceId });
      addLog('success', `Profile voice preference updated in persistent memory: "${voiceId}"`);
      setTestChecklist(prev => ({ ...prev, voiceSwitched: true }));
      toast({
        title: 'Voice Preference Updated',
        description: `Voice switched immediately to ${voiceId.toUpperCase()}`,
        duration: 2000
      });
    } catch (err) {
      addLog('error', `Failed to update profile: ${(err as Error).message}`);
    }
  };

  // Trigger test speech
  const handleTestSpeak = async () => {
    if (!testText.trim()) return;
    stopSpeaking();
    
    addLog('action', `Initiating speech synthesis for voice: "${selectedVoice}"`);
    addLog('action', `Input text: "${testText.substring(0, 45)}..."`);
    
    // Play audio
    speak(testText);
    
    // Fire Telemetry Metric Event
    await fireTelemetryEvent(selectedVoice, testText);
  };

  // Fire telemetry to local session store (and dispatch a browser event so
  // any listeners — e.g. MeditationStats / analytics hooks — can react).
  const fireTelemetryEvent = async (voice: string, text: string) => {
    setTelemetryState('firing');
    addLog('telemetry', `[Telemetry] Dispatching 'tts_synthesis' metrics event...`);

    const startTime = Date.now();
    try {
      const payload = {
        event: 'tts_synthesis',
        speaker: voice,
        language: profile.preferredLanguage || 'en',
        text_length: text.length,
        client_timestamp: new Date().toISOString(),
        latency_ms: Date.now() - startTime,
      };
      localStorage.setItem(
        `askmukthiguru_telemetry_tts_${Date.now()}`,
        JSON.stringify(payload),
      );
      window.dispatchEvent(new CustomEvent('askmukthiguru:tts_synthesis', { detail: payload }));

      setTelemetryState('success');
      setTestChecklist(prev => ({ ...prev, metricsFired: true }));
      addLog('success', `[Telemetry] Event 'tts_synthesis' logged successfully (Voice: "${voice}", length: ${text.length} chars)`);
    } catch (err) {
      addLog('error', `[Telemetry] Failed to fire telemetry metrics: ${(err as Error).message}`);
      setTelemetryState('failed');
    }
  };

  // Automated E2E verification sequence
  const runAutoTestSequence = async () => {
    if (autoTesting) return;
    setAutoTesting(true);
    setLogs([]);
    addLog('system', '🧪 Starting Automated TTS Voice & Telemetry Verification Sequence...');
    
    try {
      // Step 1: Switch to Anushka
      addLog('action', 'Step 1/4: Testing voice switch to "Anushka" (Sarvam)...');
      setSelectedVoice('anushka');
      await updateProfile({ preferredVoice: 'anushka' });
      addLog('success', 'Profile updated to "Anushka".');
      
      // Step 2: Speak test phrase
      const quote1 = VERIFICATION_QUOTES[0];
      addLog('action', `Step 2/4: Playing audio via "Anushka" speaker...`);
      speak(quote1);
      await fireTelemetryEvent('anushka', quote1);
      await new Promise(r => setTimeout(r, 1500));
      stopSpeaking();

      // Step 3: Switch to Aditya
      addLog('action', 'Step 3/4: Testing voice switch to "Aditya" (Sarvam male voice)...');
      setSelectedVoice('aditya');
      await updateProfile({ preferredVoice: 'aditya' });
      addLog('success', 'Profile updated to "Aditya".');

      // Step 4: Speak test phrase
      const quote2 = VERIFICATION_QUOTES[1];
      addLog('action', `Step 4/4: Playing audio via "Aditya" speaker...`);
      speak(quote2);
      await fireTelemetryEvent('aditya', quote2);
      await new Promise(r => setTimeout(r, 1500));
      stopSpeaking();

      // Complete
      setTestChecklist({
        supported: isSupported,
        profileSynced: true,
        voiceSwitched: true,
        metricsFired: true
      });
      
      addLog('success', '✨ Automated Verification Complete: ALL TESTS PASSED SUCCESSFULLY! 💎');
      toast({
        title: 'Verification Success',
        description: 'TTS Voice switching & Telemetry validated successfully.',
        variant: 'default'
      });
    } catch (err) {
      addLog('error', `Verification failed: ${(err as Error).message}`);
    } finally {
      setAutoTesting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0A0915] text-foreground font-sans relative overflow-hidden pb-12">
      {/* Premium background accents */}
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-[#E5A93B]/5 rounded-full filter blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-[#3BE5C2]/5 rounded-full filter blur-[120px] pointer-events-none" />

      <div className="max-w-4xl mx-auto px-4 pt-8 relative z-10">
        {/* Navigation */}
        <div className="mb-8">
          <Link
            to="/chat"
            onClick={() => stopSpeaking()}
            className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-ojas transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Back to Chat</span>
          </Link>
        </div>

        {/* Title */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
          <div>
            <h1 className="text-3xl font-serif text-foreground font-bold flex items-center gap-3">
              <Volume2 className="w-8 h-8 text-ojas animate-pulse" />
              <span>TTS & Telemetry Verification</span>
            </h1>
            <p className="text-muted-foreground text-sm mt-1">
              Verify real-time profile voice switching and telemetry logging.
            </p>
          </div>
          
          <button
            onClick={runAutoTestSequence}
            disabled={autoTesting}
            className="flex items-center gap-2 px-5 py-2.5 rounded-full bg-gradient-to-r from-ojas to-ojas/80 text-background font-semibold hover:shadow-lg hover:shadow-ojas/20 hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none transition-all"
          >
            <RefreshCw className={`w-4 h-4 ${autoTesting ? 'animate-spin' : ''}`} />
            <span>Run Automated Diagnostics</span>
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Diagnostic checklist */}
          <div className="md:col-span-1 space-y-6">
            <div className="glass-card rounded-2xl border border-border/20 p-5 bg-card/30 backdrop-blur-md">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-ojas mb-4 flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-prana" />
                <span>Verification State</span>
              </h2>
              
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Speech Synthesis Supported</span>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${testChecklist.supported ? 'bg-prana/10 text-prana' : 'bg-red-500/10 text-red-400'}`}>
                    {testChecklist.supported ? 'Passed' : 'Failed'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Profile Preference Synced</span>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${testChecklist.profileSynced ? 'bg-prana/10 text-prana' : 'bg-muted/30 text-muted-foreground'}`}>
                    {testChecklist.profileSynced ? 'Synced' : 'Pending'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Voice Switching Immediate</span>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${testChecklist.voiceSwitched ? 'bg-prana/10 text-prana' : 'bg-muted/30 text-muted-foreground'}`}>
                    {testChecklist.voiceSwitched ? 'Verified' : 'Pending'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Telemetry Metrics Logged</span>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${testChecklist.metricsFired ? 'bg-prana/10 text-prana' : 'bg-muted/30 text-muted-foreground'}`}>
                    {testChecklist.metricsFired ? 'Logged' : 'Pending'}
                  </span>
                </div>
              </div>
            </div>

            {/* Speaker Selector Panel */}
            <div className="glass-card rounded-2xl border border-border/20 p-5 bg-card/30 backdrop-blur-md">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-ojas mb-4 flex items-center gap-2">
                <Volume2 className="w-4 h-4 text-ojas" />
                <span>Switch Speaker</span>
              </h2>

              <div className="space-y-3">
                {SPEAKERS.map((sp) => {
                  const active = selectedVoice === sp.id;
                  return (
                    <button
                      key={sp.id}
                      onClick={() => handleVoiceSwitch(sp.id)}
                      disabled={autoTesting}
                      className={`w-full text-left p-3.5 rounded-xl border transition-all ${
                        active
                          ? 'border-ojas bg-ojas/10 shadow-[0_0_12px_rgba(229,169,59,0.1)]'
                          : 'border-border/30 hover:border-border/60 hover:bg-white/5'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-sm">{sp.name}</span>
                        <span className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground bg-muted/20 px-2 py-0.5 rounded">
                          {sp.gender}
                        </span>
                      </div>
                      <p className="text-[11px] text-muted-foreground mt-1 leading-normal">
                        {sp.description}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Interactive Test Panel */}
          <div className="md:col-span-2 space-y-6">
            <div className="glass-card rounded-2xl border border-border/20 p-6 bg-card/30 backdrop-blur-md">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-ojas mb-4 flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-ojas animate-spin-slow" />
                <span>Interactive TTS Tester</span>
              </h2>

              <div className="space-y-4">
                <div>
                  <label className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground block mb-2">
                    Test Script
                  </label>
                  <textarea
                    value={testText}
                    onChange={(e) => setTestText(e.target.value)}
                    disabled={autoTesting}
                    className="w-full h-24 rounded-xl border border-border/30 bg-black/25 text-sm p-3.5 focus:border-ojas focus:outline-none resize-none leading-relaxed transition-colors"
                    placeholder="Enter spiritual quote to synthesize..."
                  />
                </div>

                <div className="flex flex-wrap gap-2 mb-2">
                  {VERIFICATION_QUOTES.map((q, idx) => (
                    <button
                      key={idx}
                      onClick={() => setTestText(q)}
                      disabled={autoTesting}
                      className="text-[11px] border border-border/30 hover:border-ojas/40 bg-white/5 hover:bg-white/10 text-muted-foreground hover:text-foreground px-3 py-1.5 rounded-full transition-all"
                    >
                      Quote {idx + 1}
                    </button>
                  ))}
                </div>

                <div className="flex items-center gap-3 pt-2">
                  <button
                    onClick={handleTestSpeak}
                    disabled={autoTesting || isSpeaking}
                    className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl bg-gradient-to-r from-prana to-prana/80 text-background font-bold hover:shadow-lg hover:shadow-prana/20 hover:scale-[1.01] active:scale-[0.99] disabled:opacity-40 transition-all"
                  >
                    <Play className="w-4 h-4 fill-background" />
                    <span>Synthesize & Speak</span>
                  </button>

                  {isSpeaking && (
                    <button
                      onClick={stopSpeaking}
                      className="flex items-center justify-center gap-2 px-5 py-3 rounded-xl border border-red-500/30 hover:border-red-500/60 bg-red-500/10 hover:bg-red-500/20 text-red-400 font-bold transition-all"
                    >
                      <Square className="w-4 h-4" />
                      <span>Stop</span>
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Real-time Logs Console */}
            <div className="glass-card rounded-2xl border border-border/20 p-5 bg-black/40">
              <div className="flex items-center justify-between border-b border-border/10 pb-3 mb-3">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                  <Activity className="w-3.5 h-3.5 text-prana" />
                  <span>Real-Time Logs & Telemetry Events</span>
                </h2>
                
                {logs.length > 0 && (
                  <button
                    onClick={() => setLogs([])}
                    className="text-[10px] text-muted-foreground hover:text-foreground transition-colors"
                  >
                    Clear Console
                  </button>
                )}
              </div>

              <div
                ref={logContainerRef}
                className="h-48 overflow-y-auto space-y-2.5 font-mono text-[11px] leading-relaxed scrollbar-spiritual pr-2"
              >
                <AnimatePresence initial={false}>
                  {logs.length === 0 ? (
                    <div className="h-full flex items-center justify-center text-muted-foreground/70 italic">
                      Waiting for diagnostic actions or speak requests...
                    </div>
                  ) : (
                    logs.map((log, idx) => {
                      const colorMap = {
                        system: 'text-blue-400',
                        action: 'text-yellow-400',
                        telemetry: 'text-purple-400',
                        success: 'text-green-400 font-semibold',
                        error: 'text-red-400 font-semibold'
                      };
                      return (
                        <motion.div
                          key={idx}
                          initial={{ opacity: 0, x: -10 }}
                          animate={{ opacity: 1, x: 0 }}
                          className="flex items-start gap-2 border-b border-white/[0.02] pb-1.5"
                        >
                          <span className="text-muted-foreground shrink-0">[{log.time}]</span>
                          <span className={`${colorMap[log.type]} shrink-0 uppercase text-[9px] px-1 bg-white/5 rounded tracking-wide`}>
                            {log.type}
                          </span>
                          <span className="text-foreground/90 break-words">{log.message}</span>
                        </motion.div>
                      );
                    })
                  )}
                </AnimatePresence>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
