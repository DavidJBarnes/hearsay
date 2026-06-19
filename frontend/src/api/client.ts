// Typed API client for the Hearsay gateway.
//
// The API key is held in localStorage and sent as a bearer token. All network
// access for the console goes through this module so components stay decoupled
// from transport details.

import type {
  Job,
  RealtimeMessage,
  SpeechRequest,
  TranscriptionResponse,
  Voice,
} from './types';

const KEY_STORAGE = 'hearsay.apiKey';

export function getApiKey(): string {
  return localStorage.getItem(KEY_STORAGE) ?? '';
}

export function setApiKey(key: string): void {
  localStorage.setItem(KEY_STORAGE, key);
}

function authHeaders(json = false): Record<string, string> {
  const headers: Record<string, string> = { Authorization: `Bearer ${getApiKey()}` };
  if (json) headers['Content-Type'] = 'application/json';
  return headers;
}

async function ensureOk(resp: Response): Promise<Response> {
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = (body.detail as string) ?? detail;
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new Error(`${resp.status}: ${detail}`);
  }
  return resp;
}

export interface HearsayClient {
  synthesize(req: SpeechRequest): Promise<Blob>;
  synthesizeStreamUrl(): string;
  transcribe(file: File, model?: string, diarize?: boolean): Promise<TranscriptionResponse>;
  listVoices(): Promise<Voice[]>;
  createVoice(name: string, engine: string, reference?: File | null): Promise<Voice>;
  deleteVoice(id: string): Promise<void>;
  listJobs(): Promise<Job[]>;
  createJob(type: 'tts' | 'stt', params: Record<string, unknown>): Promise<Job>;
  metricsText(): Promise<string>;
  openRealtime(onMessage: (msg: RealtimeMessage) => void, model?: string): RealtimeSocket;
}

export interface RealtimeSocket {
  send(frame: ArrayBuffer): void;
  close(): void;
}

export const client: HearsayClient = {
  async synthesize(req: SpeechRequest): Promise<Blob> {
    const resp = await fetch('/v1/audio/speech', {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify(req),
    });
    await ensureOk(resp);
    return resp.blob();
  },

  synthesizeStreamUrl(): string {
    return '/v1/audio/speech';
  },

  async transcribe(file, model = 'whisper-1', diarize = false): Promise<TranscriptionResponse> {
    const form = new FormData();
    form.append('file', file);
    form.append('model', model);
    form.append('response_format', 'json');
    form.append('diarize', String(diarize));
    const resp = await fetch('/v1/audio/transcriptions', {
      method: 'POST',
      headers: authHeaders(),
      body: form,
    });
    await ensureOk(resp);
    return resp.json();
  },

  async listVoices(): Promise<Voice[]> {
    const resp = await fetch('/v1/voices', { headers: authHeaders() });
    await ensureOk(resp);
    return resp.json();
  },

  async createVoice(name, engine, reference): Promise<Voice> {
    const form = new FormData();
    form.append('name', name);
    form.append('engine', engine);
    if (reference) form.append('file', reference);
    const resp = await fetch('/v1/voices', {
      method: 'POST',
      headers: authHeaders(),
      body: form,
    });
    await ensureOk(resp);
    return resp.json();
  },

  async deleteVoice(id): Promise<void> {
    const resp = await fetch(`/v1/voices/${id}`, { method: 'DELETE', headers: authHeaders() });
    await ensureOk(resp);
  },

  async listJobs(): Promise<Job[]> {
    const resp = await fetch('/v1/jobs', { headers: authHeaders() });
    await ensureOk(resp);
    return resp.json();
  },

  async createJob(type, params): Promise<Job> {
    const resp = await fetch('/v1/jobs', {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify({ type, params }),
    });
    await ensureOk(resp);
    return resp.json();
  },

  async metricsText(): Promise<string> {
    const resp = await fetch('/metrics');
    await ensureOk(resp);
    return resp.text();
  },

  openRealtime(onMessage, model = 'faster-whisper'): RealtimeSocket {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${proto}://${location.host}/v1/realtime?api_key=${encodeURIComponent(
      getApiKey(),
    )}&model=${encodeURIComponent(model)}`;
    const ws = new WebSocket(url);
    ws.binaryType = 'arraybuffer';
    ws.onmessage = (ev) => {
      try {
        onMessage(JSON.parse(ev.data) as RealtimeMessage);
      } catch {
        // Ignore non-JSON frames rather than throwing out of the handler.
      }
    };
    // Surface connection failures instead of failing silently. The most common
    // cause over a self-signed HTTPS cert is the browser rejecting the wss
    // handshake until the certificate has been accepted for the site.
    ws.onerror = () =>
      onMessage({
        type: 'error',
        text:
          'Realtime connection error. Over a self-signed HTTPS cert, open the ' +
          'page and accept the certificate first, then retry.',
      });
    ws.onclose = (ev) => {
      // 1000 = normal, 1005 = no status (normal stop). Anything else is a fault.
      if (ev.code !== 1000 && ev.code !== 1005) {
        onMessage({ type: 'error', text: `Realtime connection closed (code ${ev.code}).` });
      }
    };
    return {
      send(frame: ArrayBuffer) {
        if (ws.readyState === WebSocket.OPEN) ws.send(frame);
      },
      close() {
        ws.close();
      },
    };
  },
};
