// Shared API types mirroring the backend Pydantic schemas.

export type VoiceType = 'preset' | 'cloned';

export interface Voice {
  id: string;
  name: string;
  engine: string;
  type: VoiceType;
  reference_audio_ref: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface TranscriptionSegment {
  start: number;
  end: number;
  text: string;
  speaker?: string | null;
}

export interface TranscriptionResponse {
  text: string;
  language: string | null;
  duration: number | null;
  segments: TranscriptionSegment[];
  diarization: Record<string, unknown>[] | null;
}

export type JobType = 'tts' | 'stt';

export interface Job {
  id: string;
  type: JobType;
  status: string;
  engine: string;
  params: Record<string, unknown>;
  input_ref: string | null;
  output_ref: string | null;
  error: string | null;
  timing: Record<string, number>;
  created_at: string;
  updated_at: string;
}

export interface SpeechRequest {
  model: string;
  input: string;
  voice: string;
  response_format: 'wav' | 'mp3' | 'opus' | 'flac' | 'pcm';
  speed?: number;
  stream?: boolean;
}

export type RealtimeEventType = 'partial' | 'final' | 'ready' | 'error';

export interface RealtimeMessage {
  type: RealtimeEventType;
  text: string;
  start?: number | null;
  end?: number | null;
  language?: string | null;
}
