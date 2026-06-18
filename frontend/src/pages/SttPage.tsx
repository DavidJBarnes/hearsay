import { useRef, useState } from 'react';
import { client } from '../api/client';
import type { RealtimeMessage, TranscriptionResponse } from '../api/types';
import { LiveMic } from '../components/LiveMic';

// Speech-to-text: upload a file for batch transcription, or stream the mic live.
export function SttPage() {
  const [result, setResult] = useState<TranscriptionResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [diarize, setDiarize] = useState(false);
  const [liveText, setLiveText] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  async function upload() {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError('Choose a file first');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setResult(await client.transcribe(file, 'whisper-1', diarize));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function onRealtime(msg: RealtimeMessage) {
    if (msg.type === 'partial') setLiveText(msg.text);
    else if (msg.type === 'final') setLiveText((prev) => `${prev}\n${msg.text}`.trim());
    else if (msg.type === 'error') setError(msg.text);
  }

  return (
    <section className="page">
      <h2>Speech to Text</h2>

      <div className="card">
        <h3>File transcription</h3>
        <input ref={fileRef} type="file" aria-label="audio file" accept="audio/*" />
        <label className="checkbox">
          <input
            type="checkbox"
            checked={diarize}
            onChange={(e) => setDiarize(e.target.checked)}
          />
          Diarize
        </label>
        <button disabled={busy} onClick={upload}>
          Transcribe
        </button>
        {result && (
          <div className="transcript">
            <p>{result.text}</p>
            <ul>
              {result.segments.map((s, i) => (
                <li key={i}>
                  [{s.start.toFixed(1)}–{s.end.toFixed(1)}s]
                  {s.speaker ? ` ${s.speaker}: ` : ' '}
                  {s.text}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="card">
        <h3>Live microphone</h3>
        <LiveMic onMessage={onRealtime} />
        <pre className="live-text" data-testid="live-text">
          {liveText}
        </pre>
      </div>

      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
