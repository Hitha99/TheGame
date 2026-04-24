#!/usr/bin/env python3
"""
Write theme ambient loops + UI stingers as WAV files under static/audio_themes/.
Uses only the standard library. Run from the TheGame app folder:

  python scripts/pregenerate_audio_themes.py --force

Layered harmonics, pink air, soft limiting, seamless loop crossfades — tuned for a
smooth cinematic sci-fi bed (no harsh highs; gentle saturation).
"""

from __future__ import annotations

import argparse
import math
import struct
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "audio_themes"
SR = 44100


def write_mono_wav(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        for x in samples:
            v = max(-1.0, min(1.0, x))
            w.writeframes(struct.pack("<h", int(v * 32767)))


def soft_saturate(x: float, drive: float = 1.35) -> float:
    """Gentle tanh-like curve — richer than hard clip."""
    y = x * drive
    if y > 3:
        return 0.98
    if y < -3:
        return -0.98
    return math.tanh(y)


def normalize_peak(samples: list[float], peak: float = 0.92) -> list[float]:
    m = max(abs(x) for x in samples) or 1.0
    s = peak / m
    return [x * s for x in samples]


def lcg_white(i: int, seed: int = 0xC0FFEE) -> float:
    v = (i * 1103515245 + seed + 12345) & 0x7FFFFFFF
    return (v / 0x7FFFFFFF) * 2.0 - 1.0


def pink_kellet_step(state: list[float], white: float) -> float:
    """Paul Kellet pink one step (mono)."""
    state[0] = 0.99886 * state[0] + white * 0.0555179
    state[1] = 0.99332 * state[1] + white * 0.0750759
    state[2] = 0.96900 * state[2] + white * 0.1538520
    state[3] = 0.86650 * state[3] + white * 0.3104856
    state[4] = 0.55000 * state[4] + white * 0.5329522
    state[5] = -0.7616 * state[5] - white * 0.0168980
    p = state[0] + state[1] + state[2] + state[3] + state[4] + state[5] + state[6] + white * 0.5362
    state[6] = white * 0.115926
    return p * 0.18


def smooth_one_pole(samples: list[float], coef: float = 0.974) -> None:
    """Mild low-pass in place — tames bright partials for a silkier pad."""
    y = 0.0
    for i in range(len(samples)):
        x = samples[i]
        y = coef * y + (1.0 - coef) * x
        samples[i] = y


def seamless_loop_blend(samples: list[float], fade_ms: float = 90.0) -> None:
    """In-place crossfade at loop seam to reduce clicks."""
    n = len(samples)
    f = max(2, int(SR * fade_ms / 1000.0))
    if f * 2 >= n:
        return
    for i in range(f):
        u = i / f
        a = samples[i]
        b = samples[n - f + i]
        samples[i] = a * (1.0 - u) + b * u
        samples[n - f + i] = b * (1.0 - u) + a * u


def comb_room(samples: list[float], mix: float = 0.14) -> list[float]:
    """Very short multi-tap delay = subtle space on UI sounds."""
    d1, d2 = int(0.029 * SR), int(0.043 * SR)
    b1, b2 = [0.0] * d1, [0.0] * d2
    i1 = i2 = 0
    out: list[float] = []
    for s in samples:
        t1, t2 = b1[i1], b2[i2]
        b1[i1] = s + t1 * 0.22
        b2[i2] = s + t2 * 0.18
        i1 = (i1 + 1) % d1
        i2 = (i2 + 1) % d2
        out.append(soft_saturate(s + mix * (t1 * 0.55 + t2 * 0.45)))
    return normalize_peak(out, 0.94)


def gen_ambient_qlab(seconds: float) -> list[float]:
    """Lab: sub weight, fifths, slow FM shimmer, filtered pink air."""
    n = int(SR * seconds)
    pink_s = [0.0] * 7
    out: list[float] = []
    for i in range(n):
        t = i / SR
        w = lcg_white(i, 0x5100)
        pk = pink_kellet_step(pink_s, w)
        lfo = 0.52 + 0.48 * math.sin(2 * math.pi * 0.09 * t)
        lfo2 = 0.88 + 0.12 * math.sin(2 * math.pi * 0.31 * t)
        fm_ph = 2 * math.pi * 58 * t + 0.16 * math.sin(2 * math.pi * 0.31 * t)
        fm = 0.92 * math.sin(fm_ph)
        body = (
            0.12 * fm * lfo
            + 0.062 * math.sin(2 * math.pi * 116 * t + 0.08 * math.sin(2 * math.pi * 29 * t)) * lfo * lfo2
            + 0.04 * math.sin(2 * math.pi * 174 * t + 0.12 * math.sin(2 * math.pi * 48 * t)) * lfo
            + 0.022 * math.sin(2 * math.pi * 233 * t) * lfo * 0.55
        )
        air = 0.042 * pk * (0.65 + 0.35 * math.sin(2 * math.pi * 0.042 * t))
        s = soft_saturate(body + air, 1.12)
        out.append(s)
    seamless_loop_blend(out, 105)
    smooth_one_pole(out, 0.976)
    return normalize_peak(out, 0.88)


def gen_ambient_glass(seconds: float) -> list[float]:
    """Archive: detuned chord cluster + bell-ish partials, slow swell."""
    n = int(SR * seconds)
    pink_s = [0.0] * 7
    roots = (196.0, 233.0, 294.0)
    cents = (1.004, 0.997, 1.006)  # chorus detune
    out: list[float] = []
    for i in range(n):
        t = i / SR
        w = lcg_white(i + 777, 0xA1C)
        pk = pink_kellet_step(pink_s, w)
        swell = 0.42 + 0.58 * math.sin(2 * math.pi * 0.045 * t) ** 2
        s = 0.0
        for base, ct in zip(roots, cents):
            f = base * ct
            s += 0.065 * math.sin(2 * math.pi * f * t) * swell
            s += 0.022 * math.sin(2 * math.pi * f * 2.0 * t) * swell
            s += 0.012 * math.sin(2 * math.pi * f * 3.01 * t) * swell
        s += 0.032 * pk * (0.55 + 0.45 * math.sin(2 * math.pi * 0.024 * t))
        out.append(soft_saturate(s, 1.08))
    seamless_loop_blend(out, 118)
    smooth_one_pole(out, 0.978)
    return normalize_peak(out, 0.86)


def gen_ambient_sector(seconds: float) -> list[float]:
    """Sector: pink wind, hull rumble + sub, rare distant ping."""
    n = int(SR * seconds)
    pink_s = [0.0] * 7
    out: list[float] = []
    for i in range(n):
        t = i / SR
        w = lcg_white(i + 3333, 0x5EC)
        pk = pink_kellet_step(pink_s, w)
        rumble = (
            0.095 * math.sin(2 * math.pi * 49 * t)
            + 0.042 * math.sin(2 * math.pi * 74 * t + 0.22 * math.sin(2 * math.pi * 41 * t))
        )
        wind = 0.075 * pk
        ping = 0.0
        # rare soft ping ~ every 2.4s
        cyc = (t % 2.4) / 2.4
        if 0.0 < cyc < 0.018:
            env = math.sin(math.pi * cyc / 0.018) ** 1.25
            ping = 0.034 * env * math.sin(2 * math.pi * 660 * t)
        s = soft_saturate(rumble + wind + ping, 1.1)
        out.append(s)
    seamless_loop_blend(out, 108)
    smooth_one_pole(out, 0.977)
    return normalize_peak(out, 0.87)


def gen_ui_send() -> list[float]:
    """Soft terminal tick + airy click."""
    dur = 0.085
    n = int(SR * dur)
    out: list[float] = []
    for i in range(n):
        t = i / SR
        env = math.exp(-t * 48.0)
        tick = 0.32 * env * math.sin(2 * math.pi * 1240 * t)
        body = 0.18 * env * math.sin(2 * math.pi * 415 * t + 0.8 * math.sin(2 * math.pi * 1660 * t))
        out.append(soft_saturate(tick + body, 1.4))
    return normalize_peak(comb_room(out, 0.11), 0.92)


def gen_ui_win() -> list[float]:
    """Brighter resolution arp + harmonics + short bloom."""
    freqs = (523.25, 659.25, 783.99, 1046.5)
    step = 0.068
    tail = 0.35
    n = int(SR * (step * (len(freqs) - 1) + 0.14 + tail))
    out = [0.0] * n
    for k, f in enumerate(freqs):
        t0s = k * step
        t0 = int(SR * t0s)
        hold = int(SR * 0.1)
        for j in range(hold):
            if t0 + j >= n:
                break
            tt = j / SR
            env = math.sin(min(1.0, tt / 0.028) * math.pi * 0.5) ** 1.1
            env *= math.exp(-tt * 3.2)
            ph = 2 * math.pi * f * tt
            note = 0.2 * env * (math.sin(ph) + 0.35 * math.sin(2 * ph) + 0.12 * math.sin(3 * ph))
            out[t0 + j] += note
    # bloom tail on last partial
    for j in range(int(SR * tail)):
        idx = int(SR * (step * (len(freqs) - 1) + 0.1)) + j
        if idx >= n:
            break
        tt = j / SR
        env = math.exp(-tt * 5.5) * 0.35
        ph = 2 * math.pi * 1318.5 * tt
        out[idx] += env * (math.sin(ph) + 0.25 * math.sin(2 * ph))
    return normalize_peak(comb_room(out, 0.16), 0.94)


def gen_music_qlab(seconds: float) -> list[float]:
    """Slow suspended pads + soft bass — smooth sci-fi lab (no sharp transients)."""
    n = int(SR * seconds)
    chord_len = 4.25
    chords = [
        (220.0, 277.18, 329.63),
        (174.61, 220.0, 261.63),
        (185.0, 233.08, 293.66),
        (196.0, 246.94, 311.13),
    ]
    bass_hz = (110.0, 87.31, 92.5, 98.0)
    pink_s = [0.0] * 7
    out: list[float] = []
    for i in range(n):
        t = i / SR
        seg = int(t // chord_len) % 4
        c = chords[seg]
        tl = t % chord_len
        w = lcg_white(i + 12, 0x71C)
        air = 0.018 * pink_kellet_step(pink_s, w)
        edge = min(tl, chord_len - tl)
        swell = 0.72 + 0.28 * math.sin(math.pi * edge / (chord_len * 0.5)) ** 0.85
        pad = sum(0.04 * math.sin(2 * math.pi * f * t) * swell for f in c)
        pad += sum(0.014 * math.sin(2 * math.pi * 2.005 * f * t) * swell for f in c)
        pad += sum(0.008 * math.sin(2 * math.pi * 3.01 * f * t) * swell for f in c)
        br = bass_hz[seg]
        bass = 0.062 * math.sin(2 * math.pi * br * t) * (0.58 + 0.42 * math.sin(math.pi * tl / chord_len) ** 2)
        if tl < 0.22:
            bass *= math.sin((tl / 0.22) * math.pi * 0.5) ** 0.9
        if chord_len - tl < 0.22:
            bass *= math.sin(((chord_len - tl) / 0.22) * math.pi * 0.5) ** 0.9
        out.append(soft_saturate(pad + bass + air, 1.06))
    seamless_loop_blend(out, 155)
    smooth_one_pole(out, 0.981)
    return normalize_peak(out, 0.85)


def gen_music_glass(seconds: float) -> list[float]:
    """Floating glassy cluster — slow, wide, minimal beating (smooth drift)."""
    n = int(SR * seconds)
    pink_s = [0.0] * 7
    out: list[float] = []
    for i in range(n):
        t = i / SR
        u = (t / seconds) % 1.0
        f1 = 311.0 + 9.0 * math.sin(2 * math.pi * 0.06 * t)
        f2 = 392.0 + 11.0 * math.sin(2 * math.pi * 0.052 * t + 1.1)
        f3 = 466.16 + 8.0 * math.sin(2 * math.pi * 0.044 * t + 2.0)
        s = (
            0.042 * math.sin(2 * math.pi * f1 * t)
            + 0.038 * math.sin(2 * math.pi * f2 * t + 0.35)
            + 0.034 * math.sin(2 * math.pi * f3 * t + 0.7)
        )
        s += 0.012 * math.sin(2 * math.pi * f1 * 2.002 * t)
        s += 0.009 * math.sin(2 * math.pi * 174.6 * t)
        w = lcg_white(i + 44, 0x600D)
        s += 0.024 * pink_kellet_step(pink_s, w) * (0.62 + 0.38 * math.sin(2 * math.pi * 0.031 * t + u))
        out.append(soft_saturate(s, 1.05))
    seamless_loop_blend(out, 145)
    smooth_one_pole(out, 0.982)
    return normalize_peak(out, 0.84)


def gen_music_sector(seconds: float) -> list[float]:
    """Sparse isolation: soft sub-hull + very gentle distant tones + faint halo."""
    n = int(SR * seconds)
    pink_s = [0.0] * 7
    hits = [(1.8, 55.0), (4.9, 49.0), (8.2, 65.0), (11.0, 52.0)]
    out: list[float] = []
    for i in range(n):
        t = i / SR
        w = lcg_white(i + 900, 0xCAB)
        pk = pink_kellet_step(pink_s, w)
        bed = (
            0.038 * math.sin(2 * math.pi * 38 * t)
            + 0.022 * math.sin(2 * math.pi * 57 * t + 0.15 * math.sin(2 * math.pi * 19 * t))
            + 0.014 * pk
        )
        halo = 0.012 * math.sin(2 * math.pi * 220 * t) * (0.5 + 0.5 * math.sin(2 * math.pi * 0.017 * t))
        hit = 0.0
        u = t % seconds
        for t0, hz in hits:
            du = u - t0
            if 0 <= du < 0.62:
                env = math.sin(math.pi * du / 0.62) ** 1.65
                hit += 0.028 * env * math.sin(2 * math.pi * hz * t)
        out.append(soft_saturate(bed + halo + hit, 1.08))
    seamless_loop_blend(out, 160)
    smooth_one_pole(out, 0.98)
    return normalize_peak(out, 0.86)


def gen_ui_lose() -> list[float]:
    """Low void: noise swell + descending cluster."""
    dur = 0.58
    n = int(SR * dur)
    pink_s = [0.0] * 7
    out: list[float] = []
    for i in range(n):
        t = i / SR
        u = min(1.0, t / dur)
        w = lcg_white(i + 999, 0xD00D)
        pk = pink_kellet_step(pink_s, w)
        env = math.sin(math.pi * u) ** 0.85
        f1 = 118 * ((42 / 118) ** u)
        f2 = f1 * 1.414
        ph1 = 2 * math.pi * f1 * t
        ph2 = 2 * math.pi * f2 * t
        drift = 0.14 * env * (0.55 * math.sin(ph1) + 0.45 * math.sin(ph2))
        noise = 0.1 * env * pk
        s = soft_saturate(drift + noise, 1.35)
        out.append(s)
    return normalize_peak(comb_room(out, 0.2), 0.93)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    tasks = [
        ("ambient_qlab7.wav", gen_ambient_qlab(3.6)),
        ("ambient_glass_archive.wav", gen_ambient_glass(3.6)),
        ("ambient_sector_null.wav", gen_ambient_sector(3.6)),
        ("music_qlab7.wav", gen_music_qlab(14.0)),
        ("music_glass_archive.wav", gen_music_glass(14.0)),
        ("music_sector_null.wav", gen_music_sector(14.0)),
        ("ui_send.wav", gen_ui_send()),
        ("ui_win.wav", gen_ui_win()),
        ("ui_lose.wav", gen_ui_lose()),
    ]

    for name, samples in tasks:
        dest = OUT / name
        if dest.exists() and not args.force:
            print("skip", dest.name)
            continue
        write_mono_wav(dest, samples)
        print("wrote", dest, "samples", len(samples))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
