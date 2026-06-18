// Audio helpers for the live-mic path: downsample float audio to 16 kHz and
// pack it as little-endian int16 PCM, the format the realtime endpoint expects.

const TARGET_RATE = 16000;

export function downsample(input: Float32Array, inputRate: number): Float32Array {
  if (inputRate === TARGET_RATE || inputRate <= 0) return input;
  const ratio = inputRate / TARGET_RATE;
  const outLength = Math.floor(input.length / ratio);
  const out = new Float32Array(outLength);
  for (let i = 0; i < outLength; i++) {
    out[i] = input[Math.floor(i * ratio)];
  }
  return out;
}

export function floatTo16kPcm(input: Float32Array, inputRate: number): ArrayBuffer {
  const resampled = downsample(input, inputRate);
  const buffer = new ArrayBuffer(resampled.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < resampled.length; i++) {
    const s = Math.max(-1, Math.min(1, resampled[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}
