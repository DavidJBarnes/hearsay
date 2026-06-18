import { useRef, useState } from 'react';
import { client, type RealtimeSocket } from '../api/client';
import type { RealtimeMessage } from '../api/types';
import { floatTo16kPcm } from '../audio/pcm';

interface Props {
  onMessage: (msg: RealtimeMessage) => void;
}

// Captures microphone audio, downsamples to 16 kHz PCM, and streams it over the
// realtime WebSocket. Recording state is reflected in the button label.
export function LiveMic({ onMessage }: Props) {
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const socketRef = useRef<RealtimeSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);

  async function start() {
    setError(null);
    try {
      const media = navigator.mediaDevices;
      if (!media?.getUserMedia) {
        throw new Error(
          window.isSecureContext
            ? 'Microphone not available in this browser.'
            : 'Live mic needs a secure context. Open Hearsay over HTTPS or via ' +
              'localhost (e.g. an SSH tunnel) to use the microphone. File upload ' +
              'transcription works over plain HTTP.',
        );
      }
      const stream = await media.getUserMedia({ audio: true });
      streamRef.current = stream;
      const ctx = new AudioContext();
      ctxRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const processor = ctx.createScriptProcessor(4096, 1, 1);
      const socket = client.openRealtime(onMessage);
      socketRef.current = socket;
      processor.onaudioprocess = (ev) => {
        const input = ev.inputBuffer.getChannelData(0);
        socket.send(floatTo16kPcm(input, ctx.sampleRate));
      };
      source.connect(processor);
      processor.connect(ctx.destination);
      setRecording(true);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function stop() {
    socketRef.current?.close();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    void ctxRef.current?.close();
    socketRef.current = null;
    streamRef.current = null;
    ctxRef.current = null;
    setRecording(false);
  }

  return (
    <div className="live-mic">
      <button onClick={recording ? stop : start}>
        {recording ? 'Stop' : 'Start'} recording
      </button>
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}
