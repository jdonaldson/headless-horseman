#!/usr/bin/env python3
"""Synthesize a horse neigh for the Headless Horseman. Standard library only, deterministic.

    python3 tools/make_neigh.py sounds/neigh.wav

Shape: a whinny (high, trilled, descending) that drops into a nicker (low, pulsed, breathy).
Everything is additive synthesis on one fundamental plus a band-passed breath noise, so the
file regenerates byte-for-byte and nothing here carries a sample license.
"""

import math
import random
import struct
import sys
import wave

SR = 44100
DUR = 2.0
WHINNY_END = 1.15  # seconds: where the whinny hands over to the nicker
HARMONICS = 10
TWO_PI = 2.0 * math.pi


def smoothstep(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


def formant(f):
    """Rough vocal-tract colouring: three broad resonances over a flat floor."""
    return (
        0.35
        + 0.5 * math.exp(-(((f - 1100.0) / 400.0) ** 2))
        + 1.0 * math.exp(-(((f - 2400.0) / 800.0) ** 2))
        + 0.7 * math.exp(-(((f - 3800.0) / 900.0) ** 2))
    )


class Bandpass:
    """RBJ biquad band-pass, constant 0 dB peak gain."""

    def __init__(self, f0, q):
        w0 = TWO_PI * f0 / SR
        alpha = math.sin(w0) / (2.0 * q)
        a0 = 1.0 + alpha
        self.b0 = alpha / a0
        self.b2 = -alpha / a0
        self.a1 = -2.0 * math.cos(w0) / a0
        self.a2 = (1.0 - alpha) / a0
        self.x1 = self.x2 = self.y1 = self.y2 = 0.0

    def __call__(self, x):
        y = self.b0 * x + self.b2 * self.x2 - self.a1 * self.y1 - self.a2 * self.y2
        self.x2, self.x1 = self.x1, x
        self.y2, self.y1 = self.y1, y
        return y


def render():
    rng = random.Random(1789)  # the year "The Legend of Sleepy Hollow" is set
    breath = Bandpass(3000.0, 0.8)
    n = int(SR * DUR)
    out = []
    phase = 0.0
    trill_phase = 0.0
    pulse_phase = 0.0
    jitter = 1.0
    nyquist_limit = 16000.0

    for i in range(n):
        t = i / SR

        # Fundamental trajectory.
        if t < WHINNY_END:
            u = t / WHINNY_END
            base = 1500.0 * (650.0 / 1500.0) ** u  # exponential glide 1500 -> 650 Hz
            trill_rate = 26.0 - 10.0 * u  # trill slows from 26 to 16 Hz
            trill_depth = 0.14 * (1.0 - 0.5 * u)
            pulse_depth = 0.0
            breath_level = 0.05
            level = 1.0 - 0.15 * u
        else:
            v = (t - WHINNY_END) / (DUR - WHINNY_END)
            drop = smoothstep(v / 0.18)  # fast fall into the nicker register
            base = 650.0 * (1.0 - drop) + (230.0 - 60.0 * v) * drop
            trill_rate = 16.0
            trill_depth = 0.04 * (1.0 - drop)
            pulse_depth = 0.8 * drop
            breath_level = 0.05 + 0.13 * drop
            level = 0.85 * (1.0 - drop) + 0.7 * drop

        # Slow random walk on pitch so it does not sound like an oscillator.
        jitter += rng.uniform(-0.0006, 0.0006)
        jitter = min(max(jitter, 0.985), 1.015)

        trill_phase += TWO_PI * trill_rate / SR
        pulse_phase += TWO_PI * 18.0 / SR
        f0 = base * jitter * (1.0 + trill_depth * math.sin(trill_phase))
        phase += TWO_PI * f0 / SR

        # Amplitude envelope: short attack, section level, glottal pulsing in the nicker, release.
        env = smoothstep(t / 0.04) * smoothstep((DUR - t) / 0.2) * level
        env *= 1.0 - pulse_depth * (0.5 + 0.5 * math.sin(pulse_phase))

        tone = 0.0
        for h in range(1, HARMONICS + 1):
            fh = f0 * h
            if fh > nyquist_limit:
                break
            tone += math.sin(phase * h) * formant(fh) / (h ** 0.9)

        noise = breath(rng.uniform(-1.0, 1.0)) * breath_level * 4.0
        out.append(env * (0.22 * tone + noise))

    peak = max(abs(s) for s in out) or 1.0
    gain = 0.9 / peak
    return [s * gain for s in out]


def main(path):
    samples = render()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", int(s * 32767)) for s in samples))
    print(f"wrote {path}: {len(samples) / SR:.2f}s mono 16-bit {SR} Hz")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sounds/neigh.wav")
