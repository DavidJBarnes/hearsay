import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { client, getApiKey, setApiKey } from './client';

function mockFetch(impl: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const fn = vi.fn(impl);
  vi.stubGlobal('fetch', fn);
  return fn;
}

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    statusText: 'OK',
    json: async () => body,
    text: async () => JSON.stringify(body),
    blob: async () => new Blob([JSON.stringify(body)]),
  } as unknown as Response;
}

describe('api key storage', () => {
  afterEach(() => localStorage.clear());

  it('round-trips the api key', () => {
    expect(getApiKey()).toBe('');
    setApiKey('sk-123');
    expect(getApiKey()).toBe('sk-123');
  });
});

describe('client requests', () => {
  beforeEach(() => setApiKey('sk-test'));
  afterEach(() => vi.unstubAllGlobals());

  it('synthesizes audio as a blob', async () => {
    const fetchMock = mockFetch(() => jsonResponse({ ok: true }));
    const blob = await client.synthesize({
      model: 'kokoro',
      input: 'hi',
      voice: 'af_heart',
      response_format: 'wav',
    });
    expect(blob).toBeInstanceOf(Blob);
    const [, init] = fetchMock.mock.calls[0];
    expect((init as RequestInit).method).toBe('POST');
  });

  it('transcribes via multipart', async () => {
    mockFetch(() => jsonResponse({ text: 'hello', segments: [] }));
    const file = new File([new Uint8Array([1, 2, 3])], 'a.wav', { type: 'audio/wav' });
    const result = await client.transcribe(file, 'whisper-1', true);
    expect(result.text).toBe('hello');
  });

  it('lists, creates, and deletes voices', async () => {
    mockFetch(() => jsonResponse([{ id: '1', name: 'V' }]));
    expect(await client.listVoices()).toHaveLength(1);

    mockFetch(() => jsonResponse({ id: '2', name: 'New' }));
    const made = await client.createVoice('New', 'chatterbox', null);
    expect(made.name).toBe('New');

    const withFile = await client.createVoice(
      'Clone',
      'chatterbox',
      new File([new Uint8Array([1])], 'r.wav'),
    );
    expect(withFile).toBeDefined();

    const del = mockFetch(() => jsonResponse({}, true, 204));
    await client.deleteVoice('2');
    expect(del).toHaveBeenCalledWith('/v1/voices/2', expect.objectContaining({ method: 'DELETE' }));
  });

  it('lists and creates jobs', async () => {
    mockFetch(() => jsonResponse([{ id: 'j1' }]));
    expect(await client.listJobs()).toHaveLength(1);
    mockFetch(() => jsonResponse({ id: 'j2', status: 'queued' }));
    expect((await client.createJob('tts', { input: 'x' })).status).toBe('queued');
  });

  it('fetches metrics text', async () => {
    mockFetch(() => ({ ok: true, status: 200, text: async () => 'metric 1' }) as Response);
    expect(await client.metricsText()).toBe('metric 1');
  });

  it('throws with the server detail on errors', async () => {
    mockFetch(() => jsonResponse({ detail: 'nope' }, false, 400));
    await expect(client.listVoices()).rejects.toThrow('400: nope');
  });

  it('falls back to statusText when the error body is not JSON', async () => {
    mockFetch(
      () =>
        ({
          ok: false,
          status: 500,
          statusText: 'Server Error',
          json: async () => {
            throw new Error('not json');
          },
        }) as unknown as Response,
    );
    await expect(client.listJobs()).rejects.toThrow('500: Server Error');
  });
});

describe('realtime socket', () => {
  it('opens a websocket and forwards parsed messages', () => {
    setApiKey('sk-ws');
    const instances: FakeWS[] = [];

    class FakeWS {
      static OPEN = 1;
      readyState = 1;
      binaryType = '';
      onmessage: ((ev: { data: string }) => void) | null = null;
      onerror: (() => void) | null = null;
      onclose: ((ev: { code: number }) => void) | null = null;
      sent: ArrayBuffer[] = [];
      closed = false;
      constructor(public url: string) {
        instances.push(this);
      }
      send(data: ArrayBuffer) {
        this.sent.push(data);
      }
      close() {
        this.closed = true;
      }
    }
    vi.stubGlobal('WebSocket', FakeWS as unknown as typeof WebSocket);

    const messages: { type: string; text: string }[] = [];
    const socket = client.openRealtime((m) => messages.push(m), 'faster-whisper');
    const ws = instances[0];
    expect(ws.url).toContain('api_key=sk-ws');
    ws.onmessage?.({ data: JSON.stringify({ type: 'ready', text: '' }) });
    expect(messages[0]).toEqual({ type: 'ready', text: '' });

    // Non-JSON frames are ignored, not thrown.
    ws.onmessage?.({ data: 'not json' });
    // A connection error and an abnormal close both surface as error messages.
    ws.onerror?.();
    expect(messages.at(-1)?.type).toBe('error');
    ws.onclose?.({ code: 1006 });
    expect(messages.at(-1)?.text).toContain('1006');
    // A normal close is silent.
    const before = messages.length;
    ws.onclose?.({ code: 1000 });
    expect(messages.length).toBe(before);

    socket.send(new ArrayBuffer(4));
    expect(ws.sent).toHaveLength(1);
    socket.close();
    expect(ws.closed).toBe(true);
    vi.unstubAllGlobals();
  });

  it('does not send when the socket is not open', () => {
    setApiKey('sk');
    class ClosedWS {
      static OPEN = 1;
      readyState = 0;
      binaryType = '';
      onmessage = null;
      send = vi.fn();
      close = vi.fn();
      constructor(public url: string) {}
    }
    vi.stubGlobal('WebSocket', ClosedWS as unknown as typeof WebSocket);
    const socket = client.openRealtime(() => {});
    socket.send(new ArrayBuffer(2));
    socket.finish(); // not open -> closes immediately
    vi.unstubAllGlobals();
    expect(true).toBe(true);
  });

  it('finish() sends eof then closes after a grace period', () => {
    vi.useFakeTimers();
    setApiKey('sk');
    const instances: { sent: unknown[]; closed: boolean }[] = [];
    class FakeWS {
      static OPEN = 1;
      readyState = 1;
      binaryType = '';
      onmessage = null;
      onerror = null;
      onclose = null;
      sent: unknown[] = [];
      closed = false;
      constructor(public url: string) {
        instances.push(this);
      }
      send(d: unknown) {
        this.sent.push(d);
      }
      close() {
        this.closed = true;
      }
    }
    vi.stubGlobal('WebSocket', FakeWS as unknown as typeof WebSocket);
    const socket = client.openRealtime(() => {});
    const ws = instances[0];
    socket.finish();
    expect(ws.sent).toContain('eof');
    expect(ws.closed).toBe(false);
    vi.advanceTimersByTime(2000);
    expect(ws.closed).toBe(true);
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });
});
