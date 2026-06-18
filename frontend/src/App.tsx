import { useState } from 'react';
import { ApiKeyBar } from './components/ApiKeyBar';
import { TtsPlayground } from './pages/TtsPlayground';
import { SttPage } from './pages/SttPage';
import { VoiceLibrary } from './pages/VoiceLibrary';
import { JobsPage } from './pages/JobsPage';
import { MetricsPage } from './pages/MetricsPage';

type Tab = 'tts' | 'stt' | 'voices' | 'jobs' | 'metrics';

const TABS: { id: Tab; label: string }[] = [
  { id: 'tts', label: 'TTS Playground' },
  { id: 'stt', label: 'Speech to Text' },
  { id: 'voices', label: 'Voice Library' },
  { id: 'jobs', label: 'Jobs' },
  { id: 'metrics', label: 'Metrics' },
];

// Top-level shell: API-key bar plus a simple tabbed navigation between pages.
export function App() {
  const [tab, setTab] = useState<Tab>('tts');

  return (
    <div className="app">
      <header className="app-header">
        <h1>Hearsay</h1>
        <ApiKeyBar />
      </header>
      <nav className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={t.id === tab ? 'tab active' : 'tab'}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <main className="content">
        {tab === 'tts' && <TtsPlayground />}
        {tab === 'stt' && <SttPage />}
        {tab === 'voices' && <VoiceLibrary />}
        {tab === 'jobs' && <JobsPage />}
        {tab === 'metrics' && <MetricsPage />}
      </main>
    </div>
  );
}
