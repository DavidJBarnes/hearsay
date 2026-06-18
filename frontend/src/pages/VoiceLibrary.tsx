import { useEffect, useRef, useState } from 'react';
import { client } from '../api/client';
import type { Voice } from '../api/types';

// Lists voices and lets the user create a cloned voice from a reference sample.
export function VoiceLibrary() {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [name, setName] = useState('');
  const [engine, setEngine] = useState('chatterbox');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function refresh() {
    try {
      setVoices(await client.listVoices());
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function create() {
    if (!name) {
      setError('Name is required');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const file = fileRef.current?.files?.[0] ?? null;
      await client.createVoice(name, engine, file);
      setName('');
      if (fileRef.current) fileRef.current.value = '';
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setError(null);
    try {
      await client.deleteVoice(id);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <section className="page">
      <h2>Voice Library</h2>
      <div className="card">
        <h3>Create voice</h3>
        <input
          aria-label="voice name"
          placeholder="Voice name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <select aria-label="engine" value={engine} onChange={(e) => setEngine(e.target.value)}>
          <option value="chatterbox">Chatterbox (cloning)</option>
          <option value="kokoro">Kokoro (preset)</option>
        </select>
        <input ref={fileRef} type="file" aria-label="reference sample" accept="audio/*" />
        <button disabled={busy} onClick={create}>
          Create
        </button>
      </div>

      <ul className="voice-list">
        {voices.map((v) => (
          <li key={v.id} data-testid="voice-item">
            <span className="voice-name">{v.name}</span>
            <span className={`badge badge-${v.type}`}>{v.type}</span>
            <span className="muted">{v.engine}</span>
            <button aria-label={`delete ${v.name}`} onClick={() => remove(v.id)}>
              Delete
            </button>
          </li>
        ))}
        {voices.length === 0 && <li className="muted">No voices yet.</li>}
      </ul>

      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
