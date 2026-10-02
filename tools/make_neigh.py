#!/usr/bin/env python3
"""Synthesize the Headless Horseman's horse. Standard library only, deterministic.

    python3 tools/make_neigh.py sounds/neigh.wav

Shape: a whinny (high, trilled, descending) that drops into a nicker (low, pulsed, breathy).
Nightmare dressing: a tritone shadow voice under the whinny, a sub-octave growl in the nicker,
soft-clip distortion, a low rumble, and a feedback reverb so it arrives from somewhere far
off and wrong. Everything is additive synthesis plus filtered noise, so the file regenerates
byte-for-byte and nothing here carries a sample license.
"""

import math
import random
import struct
import sys
import wave

SR = 44100
DUR = 2.6          # seconds of voice; the reverb tail runs past it
TAIL = 1.6         # seconds of reverb tail after the voice stops
WHINNY_END = 1.35  # seconds: where the whinny hands over to the nicker
HARMONICS = 12
TWO_PI = 2.0 * math.pi


def smoothstep(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


def formant(f):
    """Rough vocal-tract colouring: three broad resonances over a flat floor."""
    return (
        0.35
        + 0.5 * math.exp(-(((f - 900.0) / 400.0) ** 2))
        + 1.0 * math.exp(-(((f - 2100.0) / 800.0) ** 2))
        + 0.7 * math.exp(-(((f - 3600.0) / 900.0) ** 2))
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


class Comb:
    """Feedback comb with a one-pole low-pass in the loop: one echoing stone wall."""

    def __init__(self, delay_s, feedback, damp):
        self.buf = [0.0] * int(SR * delay_s)
        self.i = 0
        self.fb = feedback
        self.damp = damp
        self.store = 0.0

    def __call__(self, x):
        out = self.buf[self.i]
        self.store = out * (1.0 - self.damp) + self.store * self.damp
        self.buf[self.i] = x + self.store * self.fb
        self.i = (self.i + 1) % len(self.buf)
        return out


def voice(i, rng, state):
    """One sample of the dry horse. `state` carries phases and the pitch random walk."""
    t = i / SR
    if t >= DUR:
        return 0.0

    if t < WHINNY_END:
        u = t / WHINNY_END
        base = 1250.0 * (480.0 / 1250.0) ** u  # exponential glide 1250 -> 480 Hz
        trill_rate = 24.0 - 11.0 * u           # trill slows from 24 to 13 Hz
        trill_depth = 0.16 * (1.0 - 0.4 * u)
        pulse_depth = 0.0
        breath_level = 0.06
        shadow_level = 0.55 * smoothstep(u / 0.3)  # tritone voice creeps in under the whinny
        sub_level = 0.0
        level = 1.0 - 0.1 * u
    else:
        v = (t - WHINNY_END) / (DUR - WHINNY_END)
        drop = smoothstep(v / 0.16)  # fast fall into the growl register
        base = 480.0 * (1.0 - drop) + (150.0 - 55.0 * v) * drop
        trill_rate = 13.0
        trill_depth = 0.05 * (1.0 - drop)
        pulse_depth = 0.85 * drop
        breath_level = 0.06 + 0.2 * drop
        shadow_level = 0.55 * (1.0 - drop) + 0.3 * drop
        sub_level = 0.9 * drop
        level = 0.9 * (1.0 - drop) + 0.8 * drop

    state["jitter"] += rng.uniform(-0.0008, 0.0008)
    state["jitter"] = min(max(state["jitter"], 0.98), 1.02)

    state["trill"] += TWO_PI * trill_rate / SR
    state["pulse"] += TWO_PI * 11.0 / SR
    f0 = base * state["jitter"] * (1.0 + trill_depth * math.sin(state["trill"]))
    state["phase"] += TWO_PI * f0 / SR
    state["shadow"] += TWO_PI * f0 * 1.4142 * 1.003 / SR  # tritone, slightly sharp so it beats
    state["sub"] += TWO_PI * f0 * 0.5 / SR

    env = smoothstep(t / 0.05) * smoothstep((DUR - t) / 0.3) * level
    env *= 1.0 - pulse_depth * (0.5 + 0.5 * math.sin(state["pulse"]))

    tone = 0.0
    shadow = 0.0
    for h in range(1, HARMONICS + 1):
        fh = f0 * h
        if fh > 16000.0:
            break
        w = formant(fh) / (h ** 0.85)
        tone += math.sin(state["phase"] * h) * w
        if h <= 6:
            shadow += math.sin(state["shadow"] * h) * w

    sub = math.sin(state["sub"]) + 0.4 * math.sin(2.0 * state["sub"])
    breath = state["breath"](rng.uniform(-1.0, 1.0)) * breath_level * 4.0
    dry = 0.22 * (tone + shadow_level * shadow) + sub_level * 0.5 * sub + breath
    return env * dry


def render():
    rng = random.Random(1820)  # the year "The Legend of Sleepy Hollow" was published
    state = {
        "phase": 0.0, "shadow": 0.0, "sub": 0.0, "trill": 0.0, "pulse": 0.0,
        "jitter": 1.0, "breath": Bandpass(2800.0, 0.8),
    }
    rumble_filter = Bandpass(55.0, 2.5)
    combs = [Comb(0.0937, 0.72, 0.45), Comb(0.1371, 0.70, 0.5), Comb(0.2113, 0.68, 0.55)]
    echo = Comb(0.431, 0.45, 0.6)
    n = int(SR * (DUR + TAIL))
    out = []

    for i in range(n):
        t = i / SR
        dry = voice(i, rng, state)

        # Soft-clip distortion: bite without losing the pitch.
        gritty = math.tanh(2.8 * dry) / math.tanh(2.8)

        # Low rumble that swells under the whole thing and outlasts the voice.
        rumble_env = smoothstep(t / 0.6) * smoothstep((DUR + TAIL - t) / 1.2)
        rumble = rumble_filter(rng.uniform(-1.0, 1.0)) * 6.0 * 0.35 * rumble_env

        wet = sum(c(gritty) for c in combs) / len(combs) + 0.6 * echo(gritty)
        out.append(0.55 * gritty + 0.5 * wet + rumble)

    peak = max(abs(s) for s in out) or 1.0
    gain = 0.92 / peak
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
