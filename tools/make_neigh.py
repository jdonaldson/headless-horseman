#!/usr/bin/env python3
"""Synthesize a nightmare version of the Headless Horseman's horse. Standard library only,
deterministic. The default sound is a real recording; this is the optional alternate.

    python3 tools/make_neigh.py sounds/neigh-synth.wav

Shape: a whinny (high, trilled, descending) that cracks into a nicker (low, pulsed, breathy).
Nightmare dressing: a tritone shadow voice under the whinny, inharmonic partials, a sub-octave
growl in the nicker, soft-clip distortion, a low rumble, and a long, dark, damped reverb so it
arrives from somewhere far off and wrong. Everything is additive synthesis plus filtered noise,
so the file regenerates byte-for-byte and nothing here carries a sample license.

Renders in a few seconds of pure Python; there is no numpy on purpose.
"""

import math
import random
import struct
import sys
import wave

SR = 44100
DUR = 2.7          # seconds of voice; the reverb tail runs past it
TAIL = 3.4         # seconds of reverb tail after the voice stops
WHINNY_END = 1.4   # seconds: where the whinny cracks into the nicker
HARMONICS = 28
SHADOW_HARMONICS = 10
INHARMONIC = [(1.37, 0.30), (2.19, 0.22), (2.83, 0.16), (3.71, 0.12), (5.13, 0.08)]
DRIFT_LFOS = [(0.9, 0.028), (1.7, 0.02), (2.9, 0.013), (4.3, 0.007)]  # Hz, depth
TWO_PI = 2.0 * math.pi


def smoothstep(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


def bump(t, start, width):
    """Smooth hill from 0 to 1 and back, centred on start + width/2."""
    u = (t - start) / width
    return smoothstep(u * 2.0) * (1.0 - smoothstep(u * 2.0 - 1.0)) if 0.0 <= u <= 1.0 else 0.0


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


class Lowpass:
    """One-pole low-pass."""

    def __init__(self, fc):
        self.a = 1.0 - math.exp(-TWO_PI * fc / SR)
        self.y = 0.0

    def __call__(self, x):
        self.y += self.a * (x - self.y)
        return self.y


class Delay:
    """Plain circular delay line."""

    def __init__(self, delay_s):
        self.buf = [0.0] * max(1, int(SR * delay_s))
        self.i = 0

    def __call__(self, x):
        out = self.buf[self.i]
        self.buf[self.i] = x
        self.i = (self.i + 1) % len(self.buf)
        return out


class Comb:
    """Feedback comb with a one-pole low-pass in the loop: one echoing stone wall.
    High damping eats the top end on every bounce, which is what makes a reverb dark."""

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


class Allpass:
    """Schroeder all-pass diffuser: smears the comb echoes into a wash."""

    def __init__(self, delay_s, g):
        self.buf = [0.0] * int(SR * delay_s)
        self.i = 0
        self.g = g

    def __call__(self, x):
        d = self.buf[self.i]
        y = -self.g * x + d
        self.buf[self.i] = x + self.g * y
        self.i = (self.i + 1) % len(self.buf)
        return y


class Reverb:
    """Dark hall: pre-delay, four damped combs, two all-passes, a low-pass on the way out,
    and a long slapback echo for the far wall."""

    def __init__(self):
        self.pre = Delay(0.062)
        self.combs = [
            Comb(0.0997, 0.86, 0.74),
            Comb(0.1347, 0.85, 0.76),
            Comb(0.1693, 0.84, 0.78),
            Comb(0.2237, 0.83, 0.80),
        ]
        self.allpasses = [Allpass(0.0051, 0.55), Allpass(0.0167, 0.55)]
        self.tone = Lowpass(1100.0)
        self.echo = Comb(0.53, 0.5, 0.85)

    def __call__(self, x):
        x = self.pre(x)
        wet = sum(c(x) for c in self.combs) / len(self.combs)
        for a in self.allpasses:
            wet = a(wet)
        return self.tone(wet) + 0.5 * self.echo(x)


def pitch_path(t, state, rng):
    """Fundamental in Hz, plus the section parameters that ride along with it."""
    # Slow organic drift shared by both sections: four incommensurate LFOs with random
    # phases, plus a smoothed random walk so no two moments repeat.
    drift = sum(a * math.sin(TWO_PI * f * t + p) for (f, a), p in zip(DRIFT_LFOS, state["drift_phases"]))
    state["walk"] += rng.uniform(-0.0012, 0.0012)
    state["walk"] = min(max(state["walk"], -0.03), 0.03)
    organic = 1.0 + drift + state["walk"]

    if t < WHINNY_END:
        u = t / WHINNY_END
        # Onset: starts flat and swoops up past the target before settling, the way a
        # whinny is pushed out rather than switched on.
        onset = (0.74 + 0.26 * smoothstep(t / 0.11)) * (1.0 + 0.07 * bump(t, 0.06, 0.32))
        # Descent: exponential glide, but with the time axis warped so it comes down in
        # scoops instead of a straight line.
        warp = u + 0.07 * math.sin(TWO_PI * 2.2 * u) + 0.03 * math.sin(TWO_PI * 5.1 * u + 1.0)
        base = 1250.0 * (470.0 / 1250.0) ** warp * onset
        p = dict(
            trill_rate=24.0 - 11.0 * u,
            trill_depth=0.16 * (1.0 - 0.4 * u) * (0.8 + 0.2 * math.sin(TWO_PI * 2.5 * t)),
            pulse_depth=0.0,
            breath_level=0.06,
            shadow_level=0.55 * smoothstep(u / 0.3),
            sub_level=0.0,
            level=1.0 - 0.1 * u,
        )
    else:
        v = (t - WHINNY_END) / (DUR - WHINNY_END)
        drop = smoothstep(v / 0.18)
        # The crack: the voice breaks downward, overshoots below the nicker pitch, and
        # climbs back up to it.
        target = 150.0 - 55.0 * v
        base = (470.0 * (1.0 - drop) + target * drop) * (1.0 - 0.18 * math.sin(math.pi * drop))
        base *= 1.0 + 0.02 * math.sin(TWO_PI * 0.7 * t)
        p = dict(
            trill_rate=13.0,
            trill_depth=0.05 * (1.0 - drop),
            pulse_depth=0.85 * drop,
            breath_level=0.06 + 0.2 * drop,
            shadow_level=0.55 * (1.0 - drop) + 0.3 * drop,
            sub_level=0.9 * drop,
            level=0.9 * (1.0 - drop) + 0.8 * drop,
        )
    return base * organic, p


def voice(i, rng, state):
    """One sample of the dry horse. `state` carries phases and the pitch random walk."""
    t = i / SR
    if t >= DUR:
        return 0.0
    base, p = pitch_path(t, state, rng)

    state["trill"] += TWO_PI * p["trill_rate"] / SR
    state["pulse"] += TWO_PI * 11.0 / SR
    # Asymmetric trill: lingers near the top of each cycle instead of a pure sine wobble.
    trill = (math.sin(state["trill"]) + 0.35 * math.sin(2.0 * state["trill"] + 0.5)) / 1.35
    f0 = base * (1.0 + p["trill_depth"] * trill)
    state["phase"] += TWO_PI * f0 / SR
    state["shadow"] += TWO_PI * f0 * 1.4142 * 1.003 / SR  # tritone, slightly sharp so it beats
    state["sub"] += TWO_PI * f0 * 0.5 / SR
    for k, (ratio, _) in enumerate(INHARMONIC):
        state["inh"][k] += TWO_PI * f0 * ratio / SR

    env = smoothstep(t / 0.05) * smoothstep((DUR - t) / 0.3) * p["level"]
    env *= 1.0 - p["pulse_depth"] * (0.5 + 0.5 * math.sin(state["pulse"]))

    tone = 0.0
    for h in range(1, HARMONICS + 1):
        fh = f0 * h
        if fh > 16000.0:
            break
        tone += math.sin(state["phase"] * h) * formant(fh) / (h ** 0.6)
    shadow = 0.0
    for h in range(1, SHADOW_HARMONICS + 1):
        fh = f0 * 1.4142 * h
        if fh > 16000.0:
            break
        shadow += math.sin(state["shadow"] * h) * formant(fh) / (h ** 0.7)
    inharm = sum(
        math.sin(state["inh"][k]) * w * formant(f0 * ratio)
        for k, (ratio, w) in enumerate(INHARMONIC)
        if f0 * ratio < 16000.0
    )

    sub = math.sin(state["sub"]) + 0.4 * math.sin(2.0 * state["sub"])
    breath = state["breath"](rng.uniform(-1.0, 1.0)) * p["breath_level"] * 4.0
    dry = 0.16 * (tone + p["shadow_level"] * shadow + 1.2 * inharm) + p["sub_level"] * 0.5 * sub + breath
    return env * dry


def render():
    rng = random.Random(1820)  # the year "The Legend of Sleepy Hollow" was published
    state = {
        "phase": 0.0, "shadow": 0.0, "sub": 0.0, "trill": 0.0, "pulse": 0.0, "walk": 0.0,
        "inh": [0.0] * len(INHARMONIC),
        "drift_phases": [rng.uniform(0.0, TWO_PI) for _ in DRIFT_LFOS],
        "breath": Bandpass(2800.0, 0.8),
    }
    rumble_filter = Bandpass(55.0, 2.5)
    reverb = Reverb()
    n = int(SR * (DUR + TAIL))
    out = []

    for i in range(n):
        t = i / SR
        dry = voice(i, rng, state)

        # Soft-clip distortion: bite without losing the pitch.
        gritty = math.tanh(2.8 * dry) / math.tanh(2.8)

        # Low rumble that swells under the whole thing and outlasts the voice.
        rumble_env = smoothstep(t / 0.6) * smoothstep((DUR + TAIL - t) / 1.6)
        rumble = rumble_filter(rng.uniform(-1.0, 1.0)) * 6.0 * 0.35 * rumble_env

        out.append(0.42 * gritty + 0.75 * reverb(gritty) + rumble)

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
    main(sys.argv[1] if len(sys.argv) > 1 else "sounds/neigh-synth.wav")
