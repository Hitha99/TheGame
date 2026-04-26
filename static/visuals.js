/**
 * visuals.js — Scenario-aware quantum field visualizer (cinematic v3)
 *
 * Themes:
 *   lab   — orderly green particles, square grid (QLAB-7)
 *   neon  — silhouetted figure made of particles, glyph rain, wet-pavement
 *           reflection, slow color drift between pink and violet (RUNNER-2050)
 *   dust  — slow swirling motes, horizon line, drone-sweep beam (TET-7)
 *
 * Self-contained — reads state from #status-bar / #end-overlay /
 * window.selectedStory; no game.js modifications required.
 */

'use strict';

(() => {
  /* ── Themes ──────────────────────────────────────────────── */
  const THEMES = {
    lab: {
      name: 'lab',
      label: '◈ QUANTUM FIELD MONITOR',
      bg: 'rgba(10, 10, 16, 0.22)',
      palette: {
        watching:   { r: 255, g: 179, b: 71  },
        distracted: { r: 57,  g: 255, b: 132 },
        defeated:   { r: 90,  g: 90,  b: 110 },
        win:        { r: 57,  g: 255, b: 132 },
        lose:       { r: 255, g: 68,  b: 68  },
      },
      particleCount: 35,
      attractorCount: 2,
      flowMode: 'orbital',
      lattice: 'grid',
      cinematic: false,
    },
    neon: {
      name: 'neon',
      label: '◆ NEON GRID MONITOR',
      bg: 'rgba(8, 4, 20, 0.20)',
      palette: {
        watching:   { r: 255, g: 95,  b: 190 }, // hot pink
        distracted: { r: 80,  g: 220, b: 255 }, // cyan
        defeated:   { r: 100, g: 70,  b: 130 }, // dim violet
        win:        { r: 80,  g: 220, b: 255 },
        lose:       { r: 255, g: 60,  b: 100 },
      },
      altColor: { r: 140, g: 90, b: 255 },     // violet for slow drift
      particleCount: 45,
      attractorCount: 1,
      flowMode: 'rain',
      lattice: 'verticalLines',
      cinematic: true,                          // enables silhouette + reflection
    },
    dust: {
      name: 'dust',
      label: '◉ ATMOSPHERIC SCAN',
      bg: 'rgba(20, 14, 8, 0.20)',
      palette: {
        watching:   { r: 255, g: 179, b: 71  },
        distracted: { r: 230, g: 200, b: 140 },
        defeated:   { r: 110, g: 80,  b: 50  },
        win:        { r: 230, g: 200, b: 140 },
        lose:       { r: 255, g: 90,  b: 50  },
      },
      particleCount: 30,
      attractorCount: 2,
      flowMode: 'swirl',
      lattice: 'horizon',
      sweepStreak: true,
      cinematic: false,
    },
  };

  function themeForStoryId(id) {
    if (id === 'glass_archive') return THEMES.neon;
    if (id === 'sector_null')   return THEMES.dust;
    return THEMES.lab;
  }

  /* ── State ───────────────────────────────────────────────── */
  const state = {
    observer: 'watching',
    critical: false,
    inventory: '',
    room: '',
    ended: null,
    storyId: null,
    theme: THEMES.lab,
  };

  /* ── CSS ─────────────────────────────────────────────────── */
  function injectStyles() {
    if (document.getElementById('viz-styles')) return;
    const css = `
      body { overflow: hidden; }
      .terminal-wrapper { max-width: none !important; margin: 0 !important; }
      .app-layout { display: flex; height: 100vh; width: 100%; }
      .app-layout .terminal-wrapper { flex: 1 1 60%; min-width: 0; height: 100vh; }
      .viz-panel {
        flex: 1 1 40%; min-width: 320px;
        background: var(--bg-panel);
        border-left: 1px solid var(--border-hi);
        display: flex; flex-direction: column;
        height: 100vh; position: relative; overflow: hidden;
      }
      .viz-header {
        padding: 10px 18px;
        font-size: 11px; letter-spacing: 0.1em;
        color: var(--text-dim);
        border-bottom: 1px solid var(--border-hi);
        display: flex; justify-content: space-between; align-items: center;
        flex-shrink: 0;
      }
      .viz-header .viz-title { color: var(--green-dim); transition: color 0.6s; }
      .viz-header .viz-state { font-size: 10px; opacity: 0.7; }
      .viz-canvas-wrap { flex: 1 1 auto; position: relative; min-height: 0; }
      #viz-canvas { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
      .viz-readout {
        padding: 10px 18px;
        border-top: 1px solid var(--border-hi);
        font-size: 10px; letter-spacing: 0.08em;
        color: var(--text-dim); flex-shrink: 0; line-height: 1.7;
      }
      .viz-readout .lbl { color: var(--text-dim); opacity: 0.6; }
      .viz-readout .val { color: var(--green-dim); transition: color 0.6s; }
      @media (max-width: 900px) {
        body { overflow: auto; }
        .app-layout { flex-direction: column; height: auto; }
        .app-layout .terminal-wrapper { height: 70vh; flex: none; }
        .viz-panel { height: 30vh; min-width: 0; flex: none;
                     border-left: none; border-top: 1px solid var(--border-hi); }
      }
    `;
    const tag = document.createElement('style');
    tag.id = 'viz-styles';
    tag.textContent = css;
    document.head.appendChild(tag);
  }

  /* ── DOM ─────────────────────────────────────────────────── */
  function injectPanel() {
    const term = document.querySelector('.terminal-wrapper');
    if (!term) return null;
    const layout = document.createElement('div');
    layout.className = 'app-layout';
    term.parentNode.insertBefore(layout, term);
    layout.appendChild(term);
    const panel = document.createElement('aside');
    panel.className = 'viz-panel';
    panel.innerHTML = `
      <div class="viz-header">
        <span class="viz-title" id="viz-title">◈ QUANTUM FIELD MONITOR</span>
        <span class="viz-state" id="viz-state">COHERENT</span>
      </div>
      <div class="viz-canvas-wrap"><canvas id="viz-canvas"></canvas></div>
      <div class="viz-readout">
        <div><span class="lbl">FIELD:</span> <span class="val" id="viz-field">stable</span></div>
        <div><span class="lbl">PARTICLES:</span> <span class="val" id="viz-particles">—</span></div>
        <div><span class="lbl">COHERENCE:</span> <span class="val" id="viz-coherence">100%</span></div>
      </div>
    `;
    layout.appendChild(panel);
    return panel;
  }

  /* ── Particle ────────────────────────────────────────────── */
  class Particle {
    constructor(w, h, theme) { this.reset(w, h, theme, true); }
    reset(w, h, theme, initial = false) {
      this.x = Math.random() * w;
      this.y = Math.random() * h;
      const angle = Math.random() * Math.PI * 2;
      const speed = 0.8 + Math.random() * 1.2;
      if (theme.flowMode === 'rain') {
        this.vx = (Math.random() - 0.5) * 0.3;
        this.vy = 1.4 + Math.random() * 1.6;
        this.r  = 0.8 + Math.random() * 1.4;
      } else if (theme.flowMode === 'swirl') {
        this.vx = Math.cos(angle) * 0.3;
        this.vy = Math.sin(angle) * 0.3;
        this.r  = 1.4 + Math.random() * 2.4;
      } else {
        this.vx = Math.cos(angle) * speed;
        this.vy = Math.sin(angle) * speed;
        this.r  = 1.2 + Math.random() * 2.0;
      }
      this.phase = Math.random() * Math.PI * 2;
      this.life = initial ? Math.random() : 0;
      this.trail = [];
      this.maxTrail = theme.flowMode === 'rain' ? 10 : 6;
    }

    step(w, h, dt, intensity, attractors, theme) {
      this.phase += 0.05 * intensity;
      if (theme.flowMode === 'rain') {
        this.vx += (Math.random() - 0.5) * 0.05;
        this.vx *= 0.96;
        this.x += this.vx * intensity;
        this.y += this.vy * intensity;
        if (this.y > h + 10) { this.y = -10; this.x = Math.random() * w; this.trail = []; }
        if (this.x < -10) this.x = w + 10;
        if (this.x > w + 10) this.x = -10;
      } else if (theme.flowMode === 'swirl') {
        let ax = 0, ay = 0;
        for (const att of attractors) {
          const dx = att.x - this.x, dy = att.y - this.y;
          const d2 = dx * dx + dy * dy + 1;
          const f = att.strength * 0.4 / d2;
          ax += (dx + dy * 0.7) * f;
          ay += (dy - dx * 0.7) * f;
        }
        this.vx += ax * intensity * 0.6;
        this.vy += ay * intensity * 0.6;
        this.vx *= 0.98; this.vy *= 0.98;
        this.x += this.vx * intensity * 0.7;
        this.y += this.vy * intensity * 0.7;
        if (this.x < 0) { this.x = w; this.trail = []; }
        if (this.x > w) { this.x = 0; this.trail = []; }
        if (this.y < 0) { this.y = h; this.trail = []; }
        if (this.y > h) { this.y = 0; this.trail = []; }
      } else {
        const wobble = Math.sin(this.phase) * 0.5;
        let ax = 0, ay = 0;
        for (const att of attractors) {
          const dx = att.x - this.x, dy = att.y - this.y;
          const d2 = dx * dx + dy * dy + 1;
          const f = att.strength / d2;
          ax += dx * f;
          ay += dy * f;
        }
        this.vx += ax * intensity;
        this.vy += ay * intensity;
        this.vx *= 0.985; this.vy *= 0.985;
        this.x += (this.vx + wobble) * intensity;
        this.y += this.vy * intensity;
        if (this.x < 0) { this.x = w; this.trail = []; }
        if (this.x > w) { this.x = 0; this.trail = []; }
        if (this.y < 0) { this.y = h; this.trail = []; }
        if (this.y > h) { this.y = 0; this.trail = []; }
      }

      if ((this.phase * 100 | 0) % 2 === 0) {
        this.trail.push(this.x, this.y);
        if (this.trail.length > this.maxTrail * 2) this.trail.splice(0, 2);
      }
      this.life = Math.min(1, this.life + dt * 0.001);
    }

    drawTrail(ctx, color, theme) {
      if (this.trail.length < 4) return;
      const alpha = theme.flowMode === 'rain' ? 0.4 : 0.25;
      ctx.strokeStyle = `rgba(${color.r},${color.g},${color.b},${alpha})`;
      ctx.lineWidth = this.r * 0.55;
      ctx.beginPath();
      ctx.moveTo(this.trail[0], this.trail[1]);
      for (let i = 2; i < this.trail.length; i += 2) {
        ctx.lineTo(this.trail[i], this.trail[i + 1]);
      }
      ctx.stroke();
    }

    draw(ctx, color) {
      const a = this.life * (0.7 + Math.sin(this.phase) * 0.25);
      ctx.fillStyle = `rgba(${color.r},${color.g},${color.b},${a})`;
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  /* ── Cinematic layer (neon theme only) ───────────────────── */
  // Generated glyphs — invented script, drifting downward like neon ad rain
  const GLYPHS = ['♆','◈','◊','⌬','⌖','⏃','⌗','⏁','▤','▦','◬','⫷','⫸','⌭','⌸','⏚','⌿','⌫'];

  function makeGlyphRain(w, h, count) {
    return Array.from({ length: count }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      ch: GLYPHS[(Math.random() * GLYPHS.length) | 0],
      speed: 0.3 + Math.random() * 0.7,
      alpha: 0.2 + Math.random() * 0.4,
      size: 10 + Math.random() * 8,
      flicker: Math.random(),
    }));
  }

  function stepGlyphs(glyphs, w, h, dt, intensity) {
    for (const g of glyphs) {
      g.y += g.speed * intensity;
      g.flicker += dt * 0.005;
      if (g.y > h + 20) {
        g.y = -20;
        g.x = Math.random() * w;
        g.ch = GLYPHS[(Math.random() * GLYPHS.length) | 0];
      }
    }
  }

  function drawGlyphs(ctx, glyphs, color) {
    ctx.font = '14px JetBrains Mono, monospace';
    ctx.textBaseline = 'middle';
    for (const g of glyphs) {
      const flick = (Math.sin(g.flicker) * 0.5 + 0.5) * 0.7 + 0.3;
      ctx.fillStyle = `rgba(${color.r},${color.g},${color.b},${g.alpha * flick})`;
      ctx.font = `${g.size | 0}px JetBrains Mono, monospace`;
      ctx.fillText(g.ch, g.x, g.y);
    }
  }

  // Silhouette: an abstract figure made of dot-particles, breathing slowly.
  // It's just a sampled outline — not a character, not a face. A presence.
  function generateSilhouettePoints(cx, cy, scale) {
    // Parametric outline: head (circle on top), shoulders sloping down,
    // suggestion of long flowing form below. ~80 points.
    const pts = [];
    // Head — circle
    for (let i = 0; i < 26; i++) {
      const a = (i / 26) * Math.PI * 2;
      pts.push({
        ox: Math.cos(a) * 38 * scale,
        oy: -90 * scale + Math.sin(a) * 38 * scale,
      });
    }
    // Neck + shoulders
    for (let i = 0; i < 14; i++) {
      const t = i / 14;
      pts.push({
        ox: (-50 - t * 40) * scale,
        oy: (-50 + t * 30) * scale,
      });
      pts.push({
        ox: (50 + t * 40) * scale,
        oy: (-50 + t * 30) * scale,
      });
    }
    // Torso flowing outward — long form
    for (let i = 0; i < 16; i++) {
      const t = i / 16;
      const widen = 1 + t * 0.6;
      pts.push({
        ox: (-90 - t * 20) * scale * widen,
        oy: (-20 + t * 120) * scale,
      });
      pts.push({
        ox: (90 + t * 20) * scale * widen,
        oy: (-20 + t * 120) * scale,
      });
    }
    return pts.map(p => ({ ...p, x: cx + p.ox, y: cy + p.oy, jitter: Math.random() * Math.PI * 2 }));
  }

  function drawSilhouette(ctx, points, cx, cy, color, breath, w, h) {
    // Each point pulsed by breath + slight jitter so it's never static
    ctx.shadowBlur = 6;
    ctx.shadowColor = `rgba(${color.r},${color.g},${color.b},0.6)`;
    for (const p of points) {
      const j = Math.sin(p.jitter + breath * 4) * 1.5;
      const px = cx + p.ox + j;
      const py = cy + p.oy + j * 0.7 + Math.sin(breath) * 2;
      const alpha = 0.4 + Math.sin(breath + p.jitter) * 0.2;
      ctx.fillStyle = `rgba(${color.r},${color.g},${color.b},${alpha})`;
      ctx.beginPath();
      ctx.arc(px, py, 1.6, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.shadowBlur = 0;
  }

  /* ── Engine ──────────────────────────────────────────────── */
  function startEngine() {
    const canvas = document.getElementById('viz-canvas');
    const ctx    = canvas.getContext('2d', { alpha: true });
    const titleEl     = document.getElementById('viz-title');
    const stateEl     = document.getElementById('viz-state');
    const fieldEl     = document.getElementById('viz-field');
    const particlesEl = document.getElementById('viz-particles');
    const coherenceEl = document.getElementById('viz-coherence');

    let w = 0, h = 0;
    function resize() {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      w = rect.width;
      h = rect.height;
      canvas.width  = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      // Re-position silhouette on resize
      if (silhouettePoints) {
        const sc = Math.min(w, h) / 600;
        silhouettePoints = generateSilhouettePoints(w * 0.32, h * 0.5, sc);
      }
    }

    let particles = [], attractors = [], glyphs = [], silhouettePoints = null;
    function rebuildForTheme() {
      const t = state.theme;
      particles = Array.from({ length: t.particleCount }, () => new Particle(w, h, t));
      attractors = Array.from({ length: t.attractorCount }, () => ({
        x: Math.random() * w, y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.4,
        vy: (Math.random() - 0.5) * 0.4,
        strength: 8 + Math.random() * 8,
      }));
      if (t.cinematic) {
        glyphs = makeGlyphRain(w, h, 22);
        const sc = Math.min(w, h) / 600;
        silhouettePoints = generateSilhouettePoints(w * 0.32, h * 0.5, sc);
      } else {
        glyphs = [];
        silhouettePoints = null;
      }
      if (titleEl) titleEl.textContent = t.label;
      if (particlesEl) particlesEl.textContent = t.particleCount;
    }
    resize();
    window.addEventListener('resize', resize);
    rebuildForTheme();

    let burst = null;
    let collapsing = 0;
    let sweepX = -100, sweepNext = 5000;
    let lastTime = performance.now();
    let frameNo = 0;
    let running = true;

    document.addEventListener('visibilitychange', () => {
      running = !document.hidden;
      if (running) lastTime = performance.now();
    });

    function triggerBurst(color) {
      burst = { x: w / 2, y: h / 2, age: 0, max: 700, color };
    }
    function triggerCollapse() {
      collapsing = 1;
      particles.forEach(p => {
        p.vx += (w / 2 - p.x) * 0.02;
        p.vy += (h / 2 - p.y) * 0.02;
        p.trail = [];
      });
    }
    engineTriggers.burst       = triggerBurst;
    engineTriggers.collapse    = triggerCollapse;
    engineTriggers.themeChange = rebuildForTheme;

    function frame(now) {
      requestAnimationFrame(frame);
      if (!running) return;

      const dt = Math.min(now - lastTime, 50);
      lastTime = now;
      frameNo++;

      const t = state.theme;
      ctx.fillStyle = t.bg;
      ctx.fillRect(0, 0, w, h);

      // Color: blend palette with altColor for slow drift in neon theme
      let color = t.palette[state.observer] || t.palette.watching;
      if (state.ended === 'win')  color = t.palette.win;
      if (state.ended === 'lose') color = t.palette.lose;
      if (t.cinematic && t.altColor && !state.ended) {
        const drift = (Math.sin(now * 0.0003) + 1) * 0.5;  // 0..1, ~10s cycle
        color = {
          r: color.r * (1 - drift * 0.4) + t.altColor.r * (drift * 0.4),
          g: color.g * (1 - drift * 0.4) + t.altColor.g * (drift * 0.4),
          b: color.b * (1 - drift * 0.4) + t.altColor.b * (drift * 0.4),
        };
      }

      const intensity = state.ended ? 0.4
                      : state.critical ? 2.4
                      : state.observer === 'distracted' ? 1.3
                      : state.observer === 'defeated'   ? 0.6
                      : 1.3;

      attractors.forEach(a => {
        a.x += a.vx * intensity;
        a.y += a.vy * intensity;
        if (a.x < 50 || a.x > w - 50) a.vx *= -1;
        if (a.y < 50 || a.y > h - 50) a.vy *= -1;
      });

      // ───────────────────────────────────────────────────────
      // CINEMATIC NEON THEME: split rendering into upper + reflection
      // ───────────────────────────────────────────────────────
      if (t.cinematic) {
        const splitY = h * 0.72;  // wet pavement begins here

        // Upper world
        ctx.save();
        ctx.beginPath();
        ctx.rect(0, 0, w, splitY);
        ctx.clip();

        drawLattice(ctx, w, splitY, color, state.critical, now, t);

        // Glyph rain (behind silhouette)
        stepGlyphs(glyphs, w, splitY, dt, intensity * 0.7);
        drawGlyphs(ctx, glyphs.filter(g => g.y < splitY), color);

        // Silhouette
        const breath = now * 0.0008;
        if (silhouettePoints) {
          drawSilhouette(ctx, silhouettePoints, w * 0.32, h * 0.5, color, breath, w, h);
        }

        drawCore(ctx, w, h, color, state.critical, now);

        // Particles (rain) + trails
        particles.forEach(p => {
          p.step(w, splitY + 40, dt, intensity, attractors, t);
          p.drawTrail(ctx, color, t);
        });
        particles.forEach(p => p.draw(ctx, color));

        ctx.restore();

        // Reflection layer — mirror everything below splitY with darker, blurred look
        ctx.save();
        ctx.beginPath();
        ctx.rect(0, splitY, w, h - splitY);
        ctx.clip();

        ctx.translate(0, splitY * 2);
        ctx.scale(1, -1);

        ctx.globalAlpha = 0.45;

        // Re-render lattice (mirrored)
        drawLattice(ctx, w, splitY, color, state.critical, now, t);

        // Mirrored silhouette — slightly rippled
        if (silhouettePoints) {
          const ripple = Math.sin(now * 0.002) * 4;
          ctx.save();
          ctx.translate(ripple, 0);
          drawSilhouette(ctx, silhouettePoints, w * 0.32, h * 0.5, color, breath, w, h);
          ctx.restore();
        }

        // Mirrored core
        drawCore(ctx, w, h, color, state.critical, now);

        ctx.restore();

        // Wet sheen line at split
        const sheenGrad = ctx.createLinearGradient(0, splitY - 3, 0, splitY + 3);
        sheenGrad.addColorStop(0, `rgba(${color.r|0},${color.g|0},${color.b|0},0)`);
        sheenGrad.addColorStop(0.5, `rgba(${color.r|0},${color.g|0},${color.b|0},0.25)`);
        sheenGrad.addColorStop(1, `rgba(${color.r|0},${color.g|0},${color.b|0},0)`);
        ctx.fillStyle = sheenGrad;
        ctx.fillRect(0, splitY - 3, w, 6);

      } else {
        // Standard non-cinematic rendering for lab + dust themes
        drawLattice(ctx, w, h, color, state.critical, now, t);
        drawCore(ctx, w, h, color, state.critical, now);

        // Drone sweep (dust)
        if (t.sweepStreak) {
          sweepNext -= dt;
          if (sweepNext <= 0) { sweepX = -50; sweepNext = 5000 + Math.random() * 3000; }
          if (sweepX < w + 50) {
            sweepX += dt * 0.4;
            ctx.strokeStyle = `rgba(${color.r|0},${color.g|0},${color.b|0},0.45)`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(sweepX, 0);
            ctx.lineTo(sweepX, h);
            ctx.stroke();
          }
        }

        particles.forEach(p => {
          p.step(w, h, dt, intensity, attractors, t);
          p.drawTrail(ctx, color, t);
        });
        particles.forEach(p => p.draw(ctx, color));

        if (t.flowMode !== 'rain' && frameNo % 2 === 0) {
          drawEntanglement(ctx, particles, color);
        }
      }

      // Burst (item pickup) — drawn on top of everything
      if (burst) {
        burst.age += dt;
        const k = burst.age / burst.max;
        if (k >= 1) burst = null;
        else {
          const radius = k * Math.max(w, h) * 0.7;
          const a = (1 - k) * 0.7;
          ctx.strokeStyle = `rgba(${burst.color.r|0},${burst.color.g|0},${burst.color.b|0},${a})`;
          ctx.lineWidth = 3;
          ctx.beginPath();
          ctx.arc(burst.x, burst.y, radius, 0, Math.PI * 2);
          ctx.stroke();
        }
      }

      if (collapsing > 0) {
        ctx.fillStyle = `rgba(${color.r|0},${color.g|0},${color.b|0},${collapsing * 0.55})`;
        ctx.fillRect(0, 0, w, h);
        collapsing = Math.max(0, collapsing - dt * 0.0018);
      }

      // Update readout (every ~10 frames)
      if (frameNo % 10 === 0) {
        const colorStr = `rgb(${color.r|0},${color.g|0},${color.b|0})`;
        if (titleEl) titleEl.style.color = colorStr;
        if (stateEl) {
          stateEl.textContent = state.ended === 'win'  ? 'RESOLVED'
                              : state.ended === 'lose' ? 'COLLAPSE — TERMINATED'
                              : state.critical         ? 'DECOHERENCE IMMINENT'
                              : ('FIELD: ' + state.observer.toUpperCase());
        }
        if (fieldEl) {
          fieldEl.textContent = state.critical ? 'unstable' : state.observer;
          fieldEl.style.color = colorStr;
        }
        if (coherenceEl) {
          const c = state.ended === 'lose' ? 0
                  : state.ended === 'win'  ? 100
                  : state.critical          ? 25
                  : state.observer === 'defeated' ? 60
                  : state.observer === 'distracted' ? 85
                  : 100;
          coherenceEl.textContent = c + '%';
        }
      }
    }
    requestAnimationFrame(frame);
  }

  function drawLattice(ctx, w, h, color, critical, now, theme) {
    const a = critical ? 0.10 : 0.05;
    ctx.strokeStyle = `rgba(${color.r|0},${color.g|0},${color.b|0},${a})`;
    ctx.lineWidth = 1;
    ctx.beginPath();
    if (theme.lattice === 'verticalLines') {
      const cols = 14;
      for (let i = 0; i < cols; i++) {
        const x = (w * (i + 0.5)) / cols;
        ctx.moveTo(x, 0); ctx.lineTo(x, h);
      }
    } else if (theme.lattice === 'horizon') {
      const horizonY = h * 0.62;
      ctx.moveTo(0, horizonY); ctx.lineTo(w, horizonY);
      for (let i = 1; i < 3; i++) {
        const y = horizonY - i * 30;
        ctx.moveTo(0, y); ctx.lineTo(w, y);
      }
    } else {
      const spacing = 50;
      for (let x = 0; x < w; x += spacing) { ctx.moveTo(x, 0); ctx.lineTo(x, h); }
      for (let y = 0; y < h; y += spacing) { ctx.moveTo(0, y); ctx.lineTo(w, y); }
    }
    ctx.stroke();
  }

  function drawCore(ctx, w, h, color, critical, now) {
    const cx = w / 2, cy = h / 2;
    const pulse = critical ? 30 + Math.sin(now * 0.012) * 12
                           : 28 + Math.sin(now * 0.004) * 6;
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, pulse * 2);
    grad.addColorStop(0, `rgba(${color.r|0},${color.g|0},${color.b|0},0.45)`);
    grad.addColorStop(1, `rgba(${color.r|0},${color.g|0},${color.b|0},0)`);
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, pulse * 2, 0, Math.PI * 2);
    ctx.fill();
  }

  function drawEntanglement(ctx, particles, color) {
    const maxDist = 70;
    const maxDistSq = maxDist * maxDist;
    ctx.lineWidth = 1;
    ctx.strokeStyle = `rgba(${color.r|0},${color.g|0},${color.b|0},0.15)`;
    ctx.beginPath();
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        if (dx * dx + dy * dy < maxDistSq) {
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
        }
      }
    }
    ctx.stroke();
  }

  /* ── State observer ──────────────────────────────────────── */
  const engineTriggers = { burst: () => {}, collapse: () => {}, themeChange: () => {} };

  function readState() {
    const obsEl  = document.getElementById('stat-observer');
    const turnEl = document.getElementById('stat-turn');
    const invEl  = document.getElementById('stat-inv');
    const roomEl = document.getElementById('stat-room');
    const endEl  = document.getElementById('end-overlay');
    const endBox = endEl && endEl.querySelector('.end-box');

    let observer = 'watching';
    if (obsEl) {
      const cls = obsEl.className;
      if      (cls.includes('observer-defeated'))   observer = 'defeated';
      else if (cls.includes('observer-distracted')) observer = 'distracted';
    }
    return {
      observer,
      critical: !!(turnEl && turnEl.classList.contains('critical')),
      inventory: invEl ? invEl.textContent : '',
      room: roomEl ? roomEl.textContent : '',
      ended: (endEl && !endEl.classList.contains('hidden') && endBox)
              ? (endBox.classList.contains('win') ? 'win' : 'lose') : null,
      storyId: (typeof window.selectedStory !== 'undefined') ? window.selectedStory : null,
    };
  }

  function watchState() {
    function check() {
      const next = readState();
      if (next.storyId !== state.storyId) {
        state.storyId = next.storyId;
        state.theme   = themeForStoryId(next.storyId);
        engineTriggers.themeChange();
      }
      if (next.inventory !== state.inventory) {
        const oldLen = state.inventory.split(',').length;
        const newLen = next.inventory.split(',').length;
        if (newLen > oldLen && state.inventory) {
          engineTriggers.burst(state.theme.palette[next.observer] || state.theme.palette.watching);
        }
        state.inventory = next.inventory;
      }
      if (next.room !== state.room && state.room) {
        engineTriggers.collapse();
      }
      state.room = next.room;
      state.observer = next.observer;
      state.critical = next.critical;
      state.ended    = next.ended;
    }
    Object.assign(state, readState());
    state.theme = themeForStoryId(state.storyId);
    const targets = ['status-bar', 'end-overlay']
      .map(id => document.getElementById(id)).filter(Boolean);
    const mo = new MutationObserver(check);
    targets.forEach(t => mo.observe(t, {
      subtree: true, childList: true, characterData: true, attributes: true,
    }));
    setInterval(check, 700);
  }

  function init() {
    injectStyles();
    const panel = injectPanel();
    if (!panel) return;
    requestAnimationFrame(() => { startEngine(); watchState(); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
