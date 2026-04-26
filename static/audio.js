/**
 * audio.js — Background music player for QLAB-7
 *
 * Self-contained module:
 *   - Injects a MUSIC button into the existing header
 *   - Loads /static/audio/ambient.mp3 (loop, low volume)
 *   - Persists on/off state + volume in localStorage
 *   - Respects browser autoplay policy (waits for first user click)
 *
 * To use: drop royalty-free audio files into /static/audio/ and reference
 *         them in TRACKS below. Credit each track in static/audio/CREDITS.md.
 */

'use strict';

(() => {
  /* ── Configure your tracks here ─────────────────────────────
     Add as many as you want. The player picks one at random
     on page load, or you can wire this to story selection. */
  const TRACKS = [
    { src: '/static/audio/ambient.mp3', title: 'Ambient Loop' },
    // { src: '/static/audio/tension.mp3', title: 'Tension Loop' },
  ];

  const LS_MUSIC_ON  = 'qlab7_music_on';
  const LS_MUSIC_VOL = 'qlab7_music_vol';
  const DEFAULT_VOL  = 0.35;
  const FADE_MS      = 800;

  /* ── Pick a track ─────────────────────────────────────────── */
  const track = TRACKS[Math.floor(Math.random() * TRACKS.length)];

  /* ── Build the audio element ──────────────────────────────── */
  const audio = new Audio(track.src);
  audio.loop    = true;
  audio.preload = 'auto';
  audio.volume  = 0;

  /* ── Inject MUSIC button into the existing header ─────────── */
  function injectButton() {
    const headerRight = document.querySelector('.header-right');
    if (!headerRight) return null;

    const btn = document.createElement('button');
    btn.className   = 'btn-icon';
    btn.id          = 'music-btn';
    btn.title       = 'Toggle music';
    btn.setAttribute('aria-label', 'Toggle background music');
    btn.textContent = '♪ MUSIC OFF';
    // Insert before the API key button so order stays sensible
    headerRight.insertBefore(btn, headerRight.firstChild);
    return btn;
  }

  /* ── State ─────────────────────────────────────────────────── */
  function getStoredOn() {
    return localStorage.getItem(LS_MUSIC_ON) === '1';
  }
  function getStoredVol() {
    const v = parseFloat(localStorage.getItem(LS_MUSIC_VOL));
    return isNaN(v) ? DEFAULT_VOL : Math.max(0, Math.min(1, v));
  }

  let targetVol = getStoredVol();
  let isOn      = false;

  /* ── Fade helpers ─────────────────────────────────────────── */
  let fadeTimer = null;
  function fadeTo(target, ms = FADE_MS, onDone) {
    if (fadeTimer) clearInterval(fadeTimer);
    const start = audio.volume;
    const t0    = performance.now();
    fadeTimer = setInterval(() => {
      const k = Math.min(1, (performance.now() - t0) / ms);
      audio.volume = start + (target - start) * k;
      if (k >= 1) {
        clearInterval(fadeTimer);
        fadeTimer = null;
        if (onDone) onDone();
      }
    }, 30);
  }

  /* ── Toggle ────────────────────────────────────────────────── */
  async function turnOn(btn) {
    try {
      await audio.play();          // requires a user gesture the first time
      isOn = true;
      localStorage.setItem(LS_MUSIC_ON, '1');
      btn.textContent = '♪ MUSIC ON';
      fadeTo(targetVol);
    } catch (err) {
      // Autoplay blocked — user needs to click again
      console.warn('[audio] play blocked:', err);
      btn.textContent = '♪ MUSIC OFF';
    }
  }

  function turnOff(btn) {
    isOn = false;
    localStorage.setItem(LS_MUSIC_ON, '0');
    btn.textContent = '♪ MUSIC OFF';
    fadeTo(0, FADE_MS, () => audio.pause());
  }

  /* ── Init ──────────────────────────────────────────────────── */
  function init() {
    const btn = injectButton();
    if (!btn) {
      console.warn('[audio] header not found, music button skipped');
      return;
    }

    btn.addEventListener('click', () => {
      if (isOn) turnOff(btn);
      else      turnOn(btn);
    });

    // If the user had music on last session, try to resume on first
    // interaction anywhere on the page (autoplay policy compliant).
    if (getStoredOn()) {
      const resume = () => {
        turnOn(btn);
        document.removeEventListener('click', resume);
        document.removeEventListener('keydown', resume);
      };
      document.addEventListener('click',   resume, { once: false });
      document.addEventListener('keydown', resume, { once: false });
    }

    // Handle missing file gracefully
    audio.addEventListener('error', () => {
      btn.disabled    = true;
      btn.textContent = '♪ NO TRACK';
      btn.title       = `Missing file: ${track.src}`;
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
