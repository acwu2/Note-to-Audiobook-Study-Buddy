import { useState } from 'react';
import TopBar from './components/TopBar';
import SourcesPanel from './components/SourcesPanel';
import ChatPanel from './components/ChatPanel';
import StudioPanel from './components/StudioPanel';
import { useAudiobookPlayer } from './lib/useAudiobookPlayer';
import { notebookTitle, sampleAudioSeconds, sampleMessages, sampleSources } from './data/sampleNotebook';
import type { ChatMessage, Source } from './types';

type MobileTab = 'sources' | 'chat' | 'studio';

let nextId = 100;
const uid = () => String(nextId++);

export default function App() {
  const [sources, setSources] = useState<Source[]>(sampleSources);
  const [openSourceId, setOpenSourceId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>(sampleMessages);
  const [mobileTab, setMobileTab] = useState<MobileTab>('chat');
  const player = useAudiobookPlayer(sampleAudioSeconds);

  const toggleSource = (id: string) =>
    setSources((s) => s.map((x) => (x.id === id ? { ...x, enabled: !x.enabled } : x)));
  const setAllSources = (enabled: boolean) => setSources((s) => s.map((x) => ({ ...x, enabled })));

  const openSource = (id: string) => {
    setOpenSourceId(id);
    setMobileTab('sources');
  };

  // TODO: replace the pending placeholder with a call to api.ask().
  const ask = (question: string) => {
    const q = question.trim();
    if (!q) return;
    setMessages((m) => [
      ...m,
      { id: uid(), role: 'user', text: q },
      { id: uid(), role: 'pending', text: 'Your answer will appear here, grounded in the pages you have switched on.' },
    ]);
    setMobileTab('chat');
  };

  return (
    <div className="app">
      <TopBar title={notebookTitle} />

      <nav className="mobile-tabs" aria-label="Sections">
        {(['sources', 'chat', 'studio'] as MobileTab[]).map((t) => (
          <button
            key={t}
            type="button"
            aria-pressed={mobileTab === t}
            className={mobileTab === t ? 'is-active' : ''}
            onClick={() => setMobileTab(t)}
          >
            {t === 'sources' ? 'Sources' : t === 'chat' ? 'Chat' : 'Studio'}
          </button>
        ))}
      </nav>

      <main className="panels" data-mobile-tab={mobileTab}>
        <SourcesPanel
          sources={sources}
          openSourceId={openSourceId}
          onOpen={openSource}
          onClose={() => setOpenSourceId(null)}
          onToggle={toggleSource}
          onToggleAll={setAllSources}
          onListen={player.toggle}
        />
        <ChatPanel
          messages={messages}
          sources={sources}
          onAsk={ask}
          onOpenSource={openSource}
          onListen={player.toggle}
        />
        <StudioPanel pageCount={sources.length} player={player} onRunTool={ask} />
      </main>
    </div>
  );
}
