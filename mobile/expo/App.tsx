import { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  SafeAreaView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { getCapabilities, sendChat } from './src/api';
import {
  DEFAULT_RESPONSE_PREFERENCES,
  loadIncognitoStorage,
  loadPreferences,
  savePreferences,
  setIncognitoStorage,
} from './src/storage';
import type { CapabilityManifest, ChatMessage, ChatResponse, ResponsePreferences } from './src/types';

type Screen = 'today' | 'chat' | 'settings';

export default function App() {
  const [screen, setScreen] = useState<Screen>('today');
  const [capabilities, setCapabilities] = useState<CapabilityManifest>({});
  const [preferences, setPreferences] = useState<ResponsePreferences>(DEFAULT_RESPONSE_PREFERENCES);
  const [incognito, setIncognito] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void Promise.all([getCapabilities().catch(() => ({})), loadPreferences(), loadIncognitoStorage()])
      .then(([manifest, storedPreferences, storedIncognito]) => {
        setCapabilities(manifest as CapabilityManifest);
        setPreferences(storedPreferences as ResponsePreferences);
        setIncognito(storedIncognito as boolean);
      });
  }, []);

  const send = async () => {
    const userMessage = draft.trim();
    if (!userMessage || pending) return;
    setDraft('');
    setError(null);
    const nextMessages = [...messages, { role: 'user' as const, content: userMessage }];
    setMessages(nextMessages);
    setPending(true);
    try {
      const result: ChatResponse = await sendChat({
        messages: incognito ? [] : nextMessages,
        user_message: userMessage,
        language: 'en',
        incognito,
        response_preferences: {
          mode: preferences.mode,
          include_practice: preferences.includePractice,
          include_reflection: preferences.includeReflection,
          action_depth: preferences.actionDepth,
        },
      });
      setMessages((current) => [...current, { role: 'assistant', content: result.response }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reach Ask Mukthi Guru.');
    } finally {
      setPending(false);
    }
  };

  const capabilitySummary = useMemo(() => Object.keys(capabilities).filter((key) => capabilities[key] === true), [capabilities]);

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />
      <View style={styles.container}>
        {screen === 'today' && (
          <View style={styles.content}>
            <Text style={styles.eyebrow}>ASK MUKTHI GURU</Text>
            <Text style={styles.title}>A calm place to ask, reflect, and practise.</Text>
            <Text style={styles.body}>The companion uses the same backend-authoritative capabilities, evidence, safety, and privacy boundaries as the web app.</Text>
            <Pressable style={styles.primary} onPress={() => setScreen('chat')}><Text style={styles.primaryText}>Open Chat</Text></Pressable>
            <Text style={styles.caption}>{capabilitySummary.length} capabilities available from the server.</Text>
          </View>
        )}
        {screen === 'chat' && (
          <View style={styles.chat}>
            <View style={styles.chatHeader}>
              <Text style={styles.heading}>Chat</Text>
              <Pressable onPress={async () => { const next = !incognito; setIncognito(next); await setIncognitoStorage(next); }}><Text style={styles.link}>{incognito ? 'Private on' : 'Private off'}</Text></Pressable>
            </View>
            <FlatList
              style={styles.messages}
              data={messages}
              keyExtractor={(_, index) => String(index)}
              renderItem={({ item }) => <View style={[styles.bubble, item.role === 'user' ? styles.userBubble : styles.assistantBubble]}><Text style={styles.messageText}>{item.content}</Text></View>}
            />
            {error && <Text style={styles.error}>{error}</Text>}
            <View style={styles.composer}><TextInput value={draft} onChangeText={setDraft} placeholder="Ask a grounded question" placeholderTextColor="#95a59d" style={styles.input} multiline /><Pressable style={styles.send} onPress={() => void send()} disabled={pending}><Text style={styles.primaryText}>{pending ? '…' : 'Send'}</Text></Pressable></View>
          </View>
        )}
        {screen === 'settings' && (
          <View style={styles.content}>
            <Text style={styles.heading}>Response preferences</Text>
            {(['balanced_guidance', 'concise', 'reflective_guidance', 'teaching_explanation'] as const).map((mode) => <Pressable key={mode} style={styles.option} onPress={() => { const next = { ...preferences, mode }; setPreferences(next); void savePreferences(next); }}><Text style={styles.optionText}>{preferences.mode === mode ? '● ' : '○ '}{mode.replaceAll('_', ' ')}</Text></Pressable>)}
            <Pressable style={styles.option} onPress={() => { const next = { ...preferences, includePractice: !preferences.includePractice }; setPreferences(next); void savePreferences(next); }}><Text style={styles.optionText}>{preferences.includePractice ? '●' : '○'} optional practice</Text></Pressable>
            <Pressable style={styles.option} onPress={() => { const next = { ...preferences, includeReflection: !preferences.includeReflection }; setPreferences(next); void savePreferences(next); }}><Text style={styles.optionText}>{preferences.includeReflection ? '●' : '○'} reflective follow-up</Text></Pressable>
            <Pressable style={styles.linkButton} onPress={() => { setPreferences({ ...DEFAULT_RESPONSE_PREFERENCES }); void savePreferences(DEFAULT_RESPONSE_PREFERENCES); }}><Text style={styles.link}>Reset preferences</Text></Pressable>
          </View>
        )}
        <View style={styles.nav}><Pressable onPress={() => setScreen('today')}><Text style={styles.navText}>Today</Text></Pressable><Pressable onPress={() => setScreen('chat')}><Text style={styles.navText}>Chat</Text></Pressable><Pressable onPress={() => setScreen('settings')}><Text style={styles.navText}>Settings</Text></Pressable></View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#17231f' },
  container: { flex: 1, maxWidth: 720, width: '100%', alignSelf: 'center' },
  content: { flex: 1, padding: 24, justifyContent: 'center', gap: 16 },
  chat: { flex: 1, padding: 16 },
  chatHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingBottom: 12 },
  eyebrow: { color: '#b9a66b', letterSpacing: 2, fontSize: 12 },
  title: { color: '#f4f0e6', fontSize: 34, lineHeight: 42, fontWeight: '700' },
  heading: { color: '#f4f0e6', fontSize: 24, fontWeight: '700' },
  body: { color: '#cad5ce', fontSize: 16, lineHeight: 24 },
  caption: { color: '#95a59d', fontSize: 12 },
  primary: { backgroundColor: '#b9a66b', padding: 14, borderRadius: 12, alignItems: 'center' },
  primaryText: { color: '#17231f', fontWeight: '700' },
  messages: { flex: 1 },
  bubble: { padding: 12, borderRadius: 14, marginBottom: 10, maxWidth: '90%' },
  userBubble: { backgroundColor: '#2f5b4c', alignSelf: 'flex-end' },
  assistantBubble: { backgroundColor: '#24352d', alignSelf: 'flex-start' },
  messageText: { color: '#f4f0e6', fontSize: 16, lineHeight: 23 },
  composer: { flexDirection: 'row', alignItems: 'flex-end', gap: 8, paddingTop: 10 },
  input: { flex: 1, minHeight: 48, maxHeight: 120, backgroundColor: '#24352d', color: '#f4f0e6', borderRadius: 12, padding: 12 },
  send: { backgroundColor: '#b9a66b', paddingHorizontal: 16, paddingVertical: 14, borderRadius: 12 },
  error: { color: '#f6a6a6', paddingVertical: 8 },
  link: { color: '#d7c884', fontWeight: '600' },
  linkButton: { paddingVertical: 12 },
  option: { paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#395044' },
  optionText: { color: '#cad5ce', fontSize: 16 },
  nav: { flexDirection: 'row', justifyContent: 'space-around', padding: 14, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#395044' },
  navText: { color: '#d7c884', fontWeight: '600' },
});
