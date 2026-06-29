#!/usr/bin/env python3
"""
Mic spectrum probe — diagnose a recorded WAV from arecord.

Usage:
    arecord -D plughw:0,0 -f S16_LE -r 48000 -d 3 /tmp/probe.wav
    python3 mic-spectrum-probe.py /tmp/probe.wav

Output:
- Per-channel DC offset, RMS, peak, dBFS
- Top 8 spectral peaks (where the energy actually sits)
- Energy distribution by band (DC / low / voice / high)

Interpretation guide:
  Real mic signal present:    DC |mean| < 100, RMS < -35 dBFS, voice band 300-3400 Hz
                              contains the dominant spectral energy, not the DC bin.
  Open / unloaded pin:        DC |mean| > 200, RMS > -30 dBFS, energy concentrated in
                              DC + sub-200 Hz, 200-8000 Hz is flat noise floor.
  Wrong pin / wrong mux:      High RMS, but the spectrum shape matches "open pin" —
                              see the ALC295 / HDA white-noise family of bugs.

Exits non-zero if spectrum looks like the "open pin" anti-pattern.
"""
import sys, wave, struct, math


def analyze(path):
    with wave.open(path, 'rb') as w:
        sr = w.getframerate()
        nch = w.getnchannels()
        sw = w.getsampwidth()
        nf = w.getnframes()
        raw = w.readframes(nf)
    print(f"file={path}  sr={sr}  ch={nch}  sw={sw}  dur={nf/sr:.2f}s")
    fmt = {2: 'h', 4: 'i'}.get(sw)
    if not fmt:
        raise SystemExit(f"unsupported sampwidth {sw}")
    samples = struct.unpack(f'<{nf*nch}{fmt}', raw)
    chs = [samples[i::nch] for i in range(nch)]

    for i, ch in enumerate(chs):
        n = len(ch)
        mean = sum(ch) / n
        rms = math.sqrt(sum((v - mean) ** 2 for v in ch) / n)
        peak = max(abs(v) for v in ch)
        dBFS = 20 * math.log10(rms / 32768 + 1e-12) if sw == 2 else 20 * math.log10(rms / 2147483648 + 1e-12)
        print(f"  ch{i}: mean={mean:+8.1f}  RMS={rms:7.1f}  peak={peak:6d}  dBFS={dBFS:+6.2f}")

    # Crude DFT on ch0 (4096 samples is enough to see shape, not exact freq)
    N = min(len(chs[0]), 4096)
    xs = [v - sum(chs[0][:N]) / N for v in chs[0][:N]]
    mag = []
    for k in range(N // 2):
        re = sum(xs[n] * math.cos(-2 * math.pi * k * n / N) for n in range(N))
        im = sum(xs[n] * math.sin(-2 * math.pi * k * n / N) for n in range(N))
        mag.append(math.sqrt(re * re + im * im) / N)

    bin_hz = sr / N
    top = sorted(enumerate(mag), key=lambda t: -t[1])[:8]
    print("  top bins:")
    for k, m in top:
        print(f"    {k*bin_hz:7.1f} Hz   mag={m:8.1f}")

    bands = [('0-200', 0, 200), ('200-1k', 200, 1000), ('1-4k', 1000, 4000),
             ('4-8k', 4000, 8000), ('8k+', 8000, sr // 2)]
    print("  bands:")
    for label, lo, hi in bands:
        a, b = int(lo / bin_hz), int(hi / bin_hz)
        e = sum(mag[a:b]) / max(1, b - a)
        print(f"    {label:6s} Hz   avg_mag={e:8.1f}")

    # Anti-pattern detection: open / unloaded pin
    dc = abs(sum(chs[0]) / len(chs[0]))
    rms = math.sqrt(sum((v - sum(chs[0]) / len(chs[0])) ** 2 for v in chs[0]) / len(chs[0]))
    voice_avg = sum(mag[int(300 / bin_hz):int(3400 / bin_hz)]) / max(1, int(3400 / bin_hz) - int(300 / bin_hz))
    low_avg = sum(mag[:int(200 / bin_hz)]) / max(1, int(200 / bin_hz))

    if dc > 200 and voice_avg < low_avg * 0.3:
        print()
        print("⚠️  SPECTRUM LOOKS LIKE OPEN/UNLOADED PIN")
        print("    - DC offset > 200 AND voice-band energy is much smaller than low-freq energy")
        print("    - This is the classic ALC295 / HDA white-noise pattern")
        print("    - Codec is reading the bias voltage of an unconnected pin")
        print("    - Next steps: check HDA pin config, kernel fixup, try SOF driver")
        return 1
    return 0


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/probe.wav'
    sys.exit(analyze(path))
