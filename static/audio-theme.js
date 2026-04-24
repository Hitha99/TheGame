/**
 * Theme music (optional WAV beds). Ambient + UI stingers are disabled (no user toggle).
 */
'use strict';

window.GameAudioTheme = (function () {
  const LS_MUSIC_KEY = 'quantum_theme_music';
  const BASE = '/static/audio_themes/';

  /** @type {AudioContext | null} */
  let ctx = null;
  /** @type {GainNode | null} */
  let master = null;
  /** @type {BiquadFilterNode | null} Low-pass after ambient (WAV or procedural) for a smooth sci-fi tone. */
  let ambientSmoothLp = null;
  /** @type {{ stop: () => void }[]>} */
  const layers = [];
  /** @type {Promise<Record<string, AudioBuffer>> | null} */
  let decodePromise = null;
  /** @type {Record<string, AudioBuffer> | null} */
  let buffers = null;
  let themeGen = 0;
  /** @type {{ stop: () => void }[]} */
  const musicLayers = [];

  function enabled() {
    return false;
  }

  /** On unless the player explicitly turned it off (stored '0'). */
  function musicEnabled() {
    return localStorage.getItem(LS_MUSIC_KEY) !== '0';
  }

  function ensureCtx() {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    if (!ctx) ctx = new AC();
    return ctx;
  }

  function primeUserGesture() {
    const c = ensureCtx();
    if (c && c.state === 'suspended') c.resume().catch(() => {});
  }

  /**
   * Warm-decode WAVs (call on load or first gesture). Safe to call multiple times.
   */
  function preloadFiles() {
    if (decodePromise) return decodePromise;
    const c = ensureCtx();
    if (!c) {
      decodePromise = Promise.resolve({});
      return decodePromise;
    }
    const keys = ['music_qlab7', 'music_glass_archive', 'music_sector_null'];
    decodePromise = (async () => {
      const out = {};
      await Promise.all(
        keys.map(async (k) => {
          try {
            const r = await fetch(BASE + k + '.wav', { cache: 'force-cache' });
            if (!r.ok) return;
            const raw = await r.arrayBuffer();
            out[k] = await c.decodeAudioData(raw.slice(0));
          } catch (_) {}
        })
      );
      buffers = out;
      return out;
    })();
    return decodePromise;
  }

  function stopAmbientBed() {
    while (layers.length) {
      const L = layers.pop();
      try {
        L.stop();
      } catch (_) {}
    }
    if (master) {
      try {
        master.disconnect();
      } catch (_) {}
      master = null;
    }
    if (ambientSmoothLp) {
      try {
        ambientSmoothLp.disconnect();
      } catch (_) {}
      ambientSmoothLp = null;
    }
  }

  function stopMusicBed() {
    while (musicLayers.length) {
      const L = musicLayers.pop();
      try {
        L.stop();
      } catch (_) {}
    }
  }

  function stopAllThemeAudio() {
    themeGen++;
    stopAmbientBed();
    stopMusicBed();
  }

  /** Reconcile beds after toggles without nuking unrelated layers. */
  function applyThemedAudio(storyId) {
    if (!enabled() && !musicEnabled()) {
      stopAmbientBed();
      stopMusicBed();
      return;
    }
    const c = ensureCtx();
    if (!c) return;
    c.resume().catch(() => {});
    const gen = themeGen;
    preloadFiles().then(() => {
      if (gen !== themeGen) return;
      stopAmbientBed();
      if (enabled()) _loadAmbientBed(storyId, c, gen);
      stopMusicBed();
      if (musicEnabled()) _loadMusicBed(storyId, c, gen);
    });
  }

  function _trackOsc(o) {
    layers.push({
      stop() {
        try {
          o.stop();
        } catch (_) {}
        try {
          o.disconnect();
        } catch (_) {}
      },
    });
  }

  function _trackNode(stopFn) {
    layers.push({ stop: stopFn });
  }

  function _ambientKey(storyId) {
    if (storyId === 'glass_archive') return 'ambient_glass_archive';
    if (storyId === 'sector_null') return 'ambient_sector_null';
    return 'ambient_qlab7';
  }

  function _musicKey(storyId) {
    if (storyId === 'glass_archive') return 'music_glass_archive';
    if (storyId === 'sector_null') return 'music_sector_null';
    return 'music_qlab7';
  }

  function _loadAmbientBed(storyId, c, gen) {
    if (gen !== themeGen || !enabled()) return;

    const key = _ambientKey(storyId);
    const buf = buffers && buffers[key];
    const hasMusic = musicEnabled() && buffers && buffers[_musicKey(storyId)];
    if (buf) {
      master = c.createGain();
      master.gain.value = hasMusic ? 0.18 : 0.32;
      const lp = c.createBiquadFilter();
      lp.type = 'lowpass';
      lp.frequency.value = hasMusic ? 4600 : 5400;
      lp.Q.value = 0.38;
      master.connect(lp);
      lp.connect(c.destination);
      ambientSmoothLp = lp;
      const src = c.createBufferSource();
      src.buffer = buf;
      src.loop = true;
      src.connect(master);
      src.start();
      _trackNode(() => {
        try {
          src.stop();
        } catch (_) {}
        try {
          src.disconnect();
        } catch (_) {}
      });
      return;
    }

    _startProceduralAmbient(storyId, c);
  }

  function _loadMusicBed(storyId, c, gen) {
    if (gen !== themeGen || !musicEnabled()) return;
    const mkey = _musicKey(storyId);
    const mbuf = buffers && buffers[mkey];
    if (!mbuf) return;

    const g = c.createGain();
    const t0 = c.currentTime;
    const peak = 0.13;
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(peak, t0 + 0.45);
    const lp = c.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 8200;
    lp.Q.value = 0.42;
    g.connect(lp);
    lp.connect(c.destination);
    const src = c.createBufferSource();
    src.buffer = mbuf;
    src.loop = true;
    src.connect(g);
    src.start();
    musicLayers.push({
      stop() {
        try {
          src.stop();
        } catch (_) {}
        try {
          src.disconnect();
        } catch (_) {}
        try {
          g.disconnect();
        } catch (_) {}
        try {
          lp.disconnect();
        } catch (_) {}
      },
    });
  }

  /**
   * Starts ambient bed and/or looping background music (from WAVs when present).
   */
  function startThemedAudio(storyId) {
    stopAllThemeAudio();
    if (!enabled() && !musicEnabled()) return;

    const c = ensureCtx();
    if (!c) return;
    c.resume().catch(() => {});

    const gen = themeGen;
    preloadFiles().then(() => {
      if (gen !== themeGen) return;
      if (enabled()) _loadAmbientBed(storyId, c, gen);
      if (musicEnabled()) _loadMusicBed(storyId, c, gen);
    });
  }

  /** @deprecated use startThemedAudio — kept for older call sites */
  function startAmbient(storyId) {
    startThemedAudio(storyId);
  }

  function _startProceduralAmbient(storyId, c) {
    master = c.createGain();
    master.gain.value = 0.034;
    const lp = c.createBiquadFilter();
    lp.type = 'lowpass';
    if (storyId === 'glass_archive') {
      lp.frequency.value = 3400;
    } else if (storyId === 'sector_null') {
      lp.frequency.value = 2600;
    } else {
      lp.frequency.value = 3600;
    }
    lp.Q.value = 0.42;
    master.connect(lp);
    lp.connect(c.destination);
    ambientSmoothLp = lp;

    const lfo = c.createOscillator();
    lfo.type = 'sine';
    lfo.frequency.value = storyId === 'glass_archive' ? 0.045 : 0.078;
    const lfoDepth = c.createGain();
    lfoDepth.gain.value = storyId === 'glass_archive' ? 0.012 : 0.015;
    lfo.connect(lfoDepth);
    lfoDepth.connect(master.gain);
    lfo.start();
    _trackOsc(lfo);

    if (storyId === 'glass_archive') {
      _themeGlass(c);
    } else if (storyId === 'sector_null') {
      _themeSector(c);
    } else {
      _themeQlab(c);
    }
  }

  function _themeQlab(c) {
    const sub = c.createGain();
    sub.gain.value = 0.22;
    sub.connect(master);
    const o1 = c.createOscillator();
    o1.type = 'sine';
    o1.frequency.value = 55;
    o1.connect(sub);
    o1.start();
    _trackOsc(o1);
    const o2 = c.createOscillator();
    o2.type = 'sine';
    o2.frequency.value = 165;
    const g2 = c.createGain();
    g2.gain.value = 0.09;
    o2.connect(g2);
    g2.connect(master);
    o2.start();
    _trackOsc(o2);
    const o2b = c.createOscillator();
    o2b.type = 'sine';
    o2b.frequency.value = 165;
    o2b.detune.value = 4;
    const g2b = c.createGain();
    g2b.gain.value = 0.07;
    o2b.connect(g2b);
    g2b.connect(master);
    o2b.start();
    _trackOsc(o2b);
    const o3 = c.createOscillator();
    o3.type = 'sine';
    o3.frequency.value = 220;
    const g3 = c.createGain();
    g3.gain.value = 0.055;
    o3.connect(g3);
    g3.connect(master);
    o3.start();
    _trackOsc(o3);
    const o4 = c.createOscillator();
    o4.type = 'sine';
    o4.frequency.value = 330;
    const g4 = c.createGain();
    g4.gain.value = 0.018;
    o4.connect(g4);
    g4.connect(master);
    o4.start();
    _trackOsc(o4);
  }

  function _themeGlass(c) {
    const sub = c.createGain();
    sub.gain.value = 0.18;
    sub.connect(master);
    const bed = c.createOscillator();
    bed.type = 'sine';
    bed.frequency.value = 98;
    const bedG = c.createGain();
    bedG.gain.value = 0.07;
    bed.connect(bedG);
    bedG.connect(master);
    bed.start();
    _trackOsc(bed);
    [174.6, 196, 233, 294].forEach((f, idx) => {
      const o = c.createOscillator();
      o.type = 'sine';
      o.frequency.value = f;
      o.detune.value = idx === 0 ? -5 : idx === 3 ? 4 : 0;
      const gg = c.createGain();
      gg.gain.value = idx === 0 ? 0.05 : 0.07;
      o.connect(gg);
      gg.connect(sub);
      o.start();
      _trackOsc(o);
    });
  }

  function _themeSector(c) {
    const rumble = c.createGain();
    rumble.gain.value = 0.16;
    rumble.connect(master);
    const o = c.createOscillator();
    o.type = 'sine';
    o.frequency.value = 62;
    o.connect(rumble);
    o.start();
    _trackOsc(o);
    const o2 = c.createOscillator();
    o2.type = 'sine';
    o2.frequency.value = 93;
    const r2 = c.createGain();
    r2.gain.value = 0.06;
    o2.connect(r2);
    r2.connect(master);
    o2.start();
    _trackOsc(o2);

    const bufLen = 2 * c.sampleRate;
    const buf = c.createBuffer(1, bufLen, c.sampleRate);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < bufLen; i++) ch[i] = Math.random() * 2 - 1;
    const src = c.createBufferSource();
    src.buffer = buf;
    src.loop = true;
    const filt = c.createBiquadFilter();
    filt.type = 'bandpass';
    filt.frequency.value = 1100;
    filt.Q.value = 0.55;
    const ng = c.createGain();
    ng.gain.value = 0.028;
    src.connect(filt);
    filt.connect(ng);
    ng.connect(master);
    src.start();
    _trackNode(() => {
      try {
        src.stop();
      } catch (_) {}
      try {
        src.disconnect();
      } catch (_) {}
    });
  }

  function _playBufferKey(key, gain) {
    const c = ensureCtx();
    if (!c) return false;
    c.resume().catch(() => {});
    const buf = buffers && buffers[key];
    if (!buf) return false;
    const g = c.createGain();
    g.gain.value = gain;
    const src = c.createBufferSource();
    src.buffer = buf;
    src.connect(g);
    g.connect(c.destination);
    src.start();
    src.stop(c.currentTime + buf.duration + 0.02);
    return true;
  }

  function playSendBlip() {
    /* Intentionally silent — no send acknowledgment beep. */
  }

  function playWinStinger() {
    /* Disabled to keep all non-music beeps/stingers silent. */
  }

  function playLoseStinger() {
    /* Disabled to keep all non-music beeps/stingers silent. */
  }

  return {
    LS_MUSIC_KEY,
    enabled,
    musicEnabled,
    primeUserGesture,
    preloadFiles,
    startThemedAudio,
    applyThemedAudio,
    startAmbient,
    stopAmbient: stopAllThemeAudio,
    playSendBlip,
    playWinStinger,
    playLoseStinger,
  };
})();
