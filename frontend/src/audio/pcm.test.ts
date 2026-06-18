import { describe, expect, it } from 'vitest';
import { downsample, floatTo16kPcm } from './pcm';

describe('pcm helpers', () => {
  it('returns input unchanged at target rate', () => {
    const input = new Float32Array([0.1, 0.2]);
    expect(downsample(input, 16000)).toBe(input);
    expect(downsample(input, 0)).toBe(input);
  });

  it('downsamples by the rate ratio', () => {
    const input = new Float32Array([0, 1, 2, 3, 4, 5]);
    const out = downsample(input, 32000); // ratio 2 -> half the samples
    expect(out.length).toBe(3);
    expect(Array.from(out)).toEqual([0, 2, 4]);
  });

  it('packs clamped int16 little-endian PCM', () => {
    const input = new Float32Array([0, 1.5, -1.5]);
    const buf = floatTo16kPcm(input, 16000);
    const view = new DataView(buf);
    expect(buf.byteLength).toBe(6);
    expect(view.getInt16(0, true)).toBe(0);
    expect(view.getInt16(2, true)).toBe(32767); // clamped +1 -> 0x7fff
    expect(view.getInt16(4, true)).toBe(-32768); // clamped -1 -> -0x8000
  });
});
