import { useEffect, useState } from 'react';
import { client } from '../api/client';
import type { Voice } from '../api/types';

const PRESET_VOICES = ['af_heart', 'af_bella', 'am_adam', 'bf_emma'];

// Text-to-speech console: enter text, pick a voice, generate (or stream) audio.
export function TtsPlayground() {
  const [text, setText] = useState('Hello from Hearsay.');
  const [voice, setVoice] = useState('af_heart');
  const [model, setModel] = useState('kokoro');
  const [format, setFormat] = useState<'wav' | 'mp3' | 'opus'>('wav');
  const [voices, setVoices] = useState<Voice[]>([]);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [streamBytes, setStreamBytes] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    client
      .listVoices()
      .then(setVoices)
      .catch(() => setVoices([]));
  }, []);

  async function generate() {
    setBusy(true);
    setError(null);
    setStreamBytes(null);
    try {
      const blob = await client.synthesize({
        model,
        input: text,
        voice,
        response_format: format,
        stream: false,
      });
      setAudioUrl(URL.createObjectURL(blob));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function streamGenerate() {
    setBusy(true);
    setError(null);
    setStreamBytes(0);
    try {
      const resp = await fetch(client.synthesizeStreamUrl(), {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${localStorage.getItem('hearsay.apiKey') ?? ''}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ model, input: text, voice, response_format: format, stream: true }),
      });
      if (!resp.ok || !resp.body) throw new Error(`stream failed: ${resp.status}`);
      const reader = resp.body.getReader();
      const chunks: Uint8Array[] = [];
      let total = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        if (value) {
          chunks.push(value);
          total += value.length;
          setStreamBytes(total);
        }
      }
      setAudioUrl(URL.createObjectURL(new Blob(chunks as BlobPart[])));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const voiceOptions = [
    ...PRESET_VOICES,
    ...voices.map((v) => v.name).filter((n) => !PRESET_VOICES.includes(n)),
  ];

  return (
    <section className="page">
      <h2>TTS Playground</h2>
      <textarea
        aria-label="text to synthesize"
        rows={4}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="row">
        <label>
          Model
          <select value={model} onChange={(e) => setModel(e.target.value)}>
            <option value="kokoro">Kokoro</option>
            <option value="chatterbox">Chatterbox</option>
          </select>
        </label>
        <label>
          Voice
          <select aria-label="voice" value={voice} onChange={(e) => setVoice(e.target.value)}>
            {voiceOptions.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          Format
          <select value={format} onChange={(e) => setFormat(e.target.value as typeof format)}>
            <option value="wav">wav</option>
            <option value="mp3">mp3</option>
            <option value="opus">opus</option>
          </select>
        </label>
      </div>
      <div className="row">
        <button disabled={busy} onClick={generate}>
          Generate
        </button>
        <button disabled={busy} onClick={streamGenerate}>
          Stream
        </button>
      </div>
      {streamBytes !== null && <p className="muted">Streamed {streamBytes} bytes</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {audioUrl && <audio data-testid="audio-player" controls src={audioUrl} />}
    </section>
  );
}
