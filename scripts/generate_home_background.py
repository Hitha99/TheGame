#!/usr/bin/env python3
"""
Generate a sci-fi SVG backdrop for the story-select screen.

  python scripts/generate_home_background.py

Output: static/home_theme_bg.svg (stdlib only; no extra pip packages).
"""

from __future__ import annotations

import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "static" / "home_theme_bg.svg"

W, H = 1920, 1080


def main() -> int:
    rng = random.Random(0x51AB7)

    stars: list[str] = []
    for _ in range(140):
        x = rng.randint(0, W)
        y = rng.randint(0, H)
        r = rng.choice((0.4, 0.6, 0.9, 1.2))
        o = rng.uniform(0.04, 0.22)
        stars.append(
            f'<circle cx="{x}" cy="{y}" r="{r:.2f}" fill="#b8e0c8" opacity="{o:.3f}"/>'
        )

    paths = (
        '<path d="M-80 720 Q480 560 960 620 T2000 580" fill="none" '
        'stroke="#39ff84" stroke-width="1.2" opacity="0.28"/>'
        '<path d="M0 840 Q560 680 1180 760 T1920 700" fill="none" '
        'stroke="#5eb8ff" stroke-width="0.9" opacity="0.22"/>'
        '<path d="M200 920 Q700 780 1280 820 T1880 880" fill="none" '
        'stroke="#c4a5f5" stroke-width="0.85" opacity="0.2"/>'
    )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid slice">
  <defs>
    <linearGradient id="deep" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#030810"/>
      <stop offset="40%" stop-color="#0a0818"/>
      <stop offset="100%" stop-color="#03060c"/>
    </linearGradient>
    <radialGradient id="gL" cx="10%" cy="42%" r="58%">
      <stop offset="0%" stop-color="#39ff84" stop-opacity="0.2"/>
      <stop offset="100%" stop-color="#000" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="gC" cx="50%" cy="28%" r="48%">
      <stop offset="0%" stop-color="#b794f6" stop-opacity="0.14"/>
      <stop offset="100%" stop-color="#000" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="gR" cx="90%" cy="44%" r="54%">
      <stop offset="0%" stop-color="#5eb8ff" stop-opacity="0.18"/>
      <stop offset="100%" stop-color="#000" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="floor" cx="50%" cy="98%" r="72%">
      <stop offset="0%" stop-color="#1a6c42" stop-opacity="0.62"/>
      <stop offset="50%" stop-color="#0d2818" stop-opacity="0.22"/>
      <stop offset="100%" stop-color="#000" stop-opacity="0"/>
    </radialGradient>
    <pattern id="grid" width="48" height="48" patternUnits="userSpaceOnUse">
      <path d="M48 0H0V48" fill="none" stroke="#2a6040" stroke-width="0.9" opacity="0.5"/>
    </pattern>
    <filter id="blur" x="-6%" y="-6%" width="112%" height="112%">
      <feGaussianBlur stdDeviation="2"/>
    </filter>
  </defs>
  <rect width="100%" height="100%" fill="url(#deep)"/>
  <rect width="100%" height="100%" fill="url(#gL)"/>
  <rect width="100%" height="100%" fill="url(#gC)"/>
  <rect width="100%" height="100%" fill="url(#gR)"/>
  <rect width="100%" height="100%" fill="url(#grid)"/>
  <rect width="100%" height="100%" fill="url(#floor)"/>
  <g filter="url(#blur)" opacity="0.85">{paths}</g>
  <g>{"".join(stars)}</g>
</svg>
"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(svg, encoding="utf-8")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
