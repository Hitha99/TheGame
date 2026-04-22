/**
 * game.js — Quantum Text Adventure frontend
 *
 * Responsibilities:
 *   - API key modal (localStorage persistence)
 *   - /api/start and /api/action communication
 *   - Typewriter text rendering with cursor
 *   - Status bar updates
 *   - Win/lose overlay
 *   - Input enable/disable during loading
 */

'use strict';

/* ── Constants ───────────────────────────────────────────── */
const LS_KEY   = 'tamus_api_key';
const TYPE_SPD = 18; // ms per character (typewriter speed)

/* ── DOM refs ────────────────────────────────────────────── */
const narrativeArea   = document.getElementById('narrative-area');
const playerInput     = document.getElementById('player-input');
const sendBtn         = document.getElementById('send-btn');
const restartBtn      = document.getElementById('restart-btn');
const loadingEl       = document.getElementById('loading-indicator');
const endOverlay      = document.getElementById('end-overlay');
const endBox          = endOverlay.querySelector('.end-box');
const endStatus       = document.getElementById('end-status');
const endMessage      = document.getElementById('end-message');
const endRestartBtn   = document.getElementById('end-restart-btn');

const statRoom        = document.getElementById('stat-room');
const statTurn        = document.getElementById('stat-turn');
const statObserver    = document.getElementById('stat-observer');
const statInv         = document.getElementById('stat-inv');
const statExits       = document.getElementById('stat-exits');
const statNarrMode    = document.getElementById('stat-narr-mode');

const apiKeyBtn       = document.getElementById('api-key-btn');
const apiModal        = document.getElementById('api-modal');
const modalCloseBtn   = document.getElementById('modal-close-btn');
const apiKeyInput     = document.getElementById('api-key-input');
const saveApiKeyBtn   = document.getElementById('save-api-key-btn');
const clearApiKeyBtn  = document.getElementById('clear-api-key-btn');
const apiKeyStatus    = document.getElementById('api-key-status');

const storyScreen = document.getElementById('story-select-screen');
const storyCards  = document.getElementById('story-cards');

/* ── State ───────────────────────────────────────────────── */
let gameActive     = false;
let typewriterBusy = false;
let selectedStory  = null;

/* ═══════════════════════════════════════════════════════════
   API KEY MODAL
   ═══════════════════════════════════════════════════════════ */

function getApiKey() {
  return localStorage.getItem(LS_KEY) || '';
}

function openModal() {
  apiKeyInput.value = getApiKey();
  apiKeyStatus.textContent = getApiKey() ? '● key saved in browser storage' : '';
  apiModal.classList.add('visible');
  apiKeyInput.focus();
}

function closeModal() {
  apiModal.classList.remove('visible');
}

function saveApiKey() {
  const key = apiKeyInput.value.trim();
  if (key) {
    localStorage.setItem(LS_KEY, key);
    apiKeyStatus.textContent = '✓ key saved';
  } else {
    localStorage.removeItem(LS_KEY);
    apiKeyStatus.textContent = 'key cleared — fallback narration active';
  }
  setTimeout(closeModal, 800);
}

function clearApiKey() {
  localStorage.removeItem(LS_KEY);
  apiKeyInput.value = '';
  apiKeyStatus.textContent = 'key cleared — fallback narration active';
}

apiKeyBtn.addEventListener('click', openModal);
modalCloseBtn.addEventListener('click', closeModal);
saveApiKeyBtn.addEventListener('click', saveApiKey);
clearApiKeyBtn.addEventListener('click', clearApiKey);

apiModal.addEventListener('click', (e) => {
  if (e.target === apiModal) closeModal();
});

apiKeyInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') saveApiKey();
  if (e.key === 'Escape') closeModal();
});

/* ═══════════════════════════════════════════════════════════
   STATUS BAR
   ═══════════════════════════════════════════════════════════ */

function updateStatusBar(state) {
  if (!state) return;

  statRoom.textContent = '◈ ' + (state.room_name || '—');

  const turn = state.turn ?? 0;
  const rem  = state.turns_remaining ?? 25;
  statTurn.textContent = `TURN ${turn}/25`;
  statTurn.classList.toggle('critical', rem <= 5);

  const obs = (state.observer_status || 'watching').toLowerCase();
  statObserver.textContent = 'OBSERVER: ' + obs.toUpperCase();
  statObserver.className = 'stat observer-' + obs;

  const inv = state.inventory && state.inventory.length
    ? state.inventory.join(', ')
    : '—';
  statInv.textContent = 'INV: ' + inv;

  const exits = state.exits && state.exits.length
    ? state.exits.join(' · ')
    : '—';
  statExits.textContent = 'EXITS: ' + exits;
}

function updateNarrMode(mode) {
  if (!statNarrMode) return;
  const labels = { ai: '◉ AI', fallback: '◎ FALLBACK', no_key: '○ NO KEY' };
  statNarrMode.textContent = 'NARR: ' + (labels[mode] || '—');
  statNarrMode.className = 'stat narr-' + (mode || 'none');
}

/* ═══════════════════════════════════════════════════════════
   TYPEWRITER RENDERER
   ═══════════════════════════════════════════════════════════ */

function typewriterRender(element, text, speed, onDone) {
  typewriterBusy = true;
  element.textContent = '';
  const cursor = document.createElement('span');
  cursor.className = 'typewriter-cursor';
  element.appendChild(cursor);

  let i = 0;
  function tick() {
    if (i < text.length) {
      element.insertBefore(document.createTextNode(text[i]), cursor);
      i++;
      setTimeout(tick, speed);
    } else {
      cursor.remove();
      typewriterBusy = false;
      if (onDone) onDone();
    }
  }
  tick();
}

/* ═══════════════════════════════════════════════════════════
   NARRATIVE ENTRY
   ═══════════════════════════════════════════════════════════ */

function appendEntry(actionText, narrativeText, variant) {
  // Remove boot screen on first entry
  const boot = document.getElementById('boot-screen');
  if (boot) boot.remove();

  const entry = document.createElement('div');
  entry.className = 'narrative-entry pulse-glow' + (variant ? ' entry-' + variant : '');

  if (actionText) {
    const actionEl = document.createElement('div');
    actionEl.className = 'entry-action';
    actionEl.textContent = actionText;
    entry.appendChild(actionEl);
  }

  const textEl = document.createElement('div');
  textEl.className = 'entry-text';
  entry.appendChild(textEl);

  narrativeArea.appendChild(entry);
  narrativeArea.scrollTop = narrativeArea.scrollHeight;

  return new Promise((resolve) => {
    typewriterRender(textEl, narrativeText, TYPE_SPD, () => {
      narrativeArea.scrollTop = narrativeArea.scrollHeight;
      resolve();
    });
  });
}

function appendDivider() {
  const hr = document.createElement('hr');
  hr.className = 'turn-divider';
  narrativeArea.appendChild(hr);
}

/* ═══════════════════════════════════════════════════════════
   LOADING STATE
   ═══════════════════════════════════════════════════════════ */

function setLoading(on) {
  loadingEl.classList.toggle('hidden', !on);
  playerInput.disabled = on || !gameActive;
  sendBtn.disabled = on || !gameActive;
}

/* ═══════════════════════════════════════════════════════════
   WIN / LOSE OVERLAY
   ═══════════════════════════════════════════════════════════ */

function showEndOverlay(status, narrative) {
  endOverlay.classList.remove('hidden');
  endBox.className = 'end-box ' + (status === 'win' ? 'win' : 'lose');
  endStatus.textContent = status === 'win'
    ? 'SIMULATION RESOLVED — ESCAPE COMPLETE'
    : 'SIMULATION TERMINATED';
  endMessage.textContent = narrative;
}

endRestartBtn.addEventListener('click', showStorySelect);
restartBtn.addEventListener('click', showStorySelect);

/* ═══════════════════════════════════════════════════════════
   STORY SELECTION
   ═══════════════════════════════════════════════════════════ */

async function showStorySelect() {
  endOverlay.classList.add('hidden');
  storyScreen.classList.remove('hidden');
  storyCards.innerHTML = '<div style="color:var(--text-dim);font-size:12px;letter-spacing:.08em">LOADING…</div>';

  try {
    const res = await fetch('/api/stories');
    const stories = await res.json();
    storyCards.innerHTML = '';
    stories.forEach(story => {
      const card = document.createElement('div');
      card.className = 'story-card';
      card.style.setProperty('--story-color', story.color);
      card.style.borderColor = story.color + '44';
      card.innerHTML = `
        <span class="story-card-icon" style="color:${story.color}">${story.icon}</span>
        <div class="story-card-title" style="color:${story.color}">${story.title}</div>
        <div class="story-card-subtitle">${story.subtitle}</div>
        <div class="story-card-tagline">${story.tagline}</div>
        <span class="story-card-select" style="color:${story.color}">[ BEGIN ]</span>
      `;
      card.addEventListener('click', () => {
        selectedStory = story.id;
        storyScreen.classList.add('hidden');
        startGame(story.id);
      });
      storyCards.appendChild(card);
    });
  } catch (err) {
    storyCards.innerHTML = `<div style="color:var(--red);font-size:12px">Failed to load stories: ${err.message}</div>`;
  }
}

/* ═══════════════════════════════════════════════════════════
   GAME START
   ═══════════════════════════════════════════════════════════ */

async function startGame(storyId) {
  // Reset UI
  endOverlay.classList.add('hidden');
  narrativeArea.innerHTML = '';
  narrativeArea.insertAdjacentHTML('beforeend', `
    <div class="boot-screen" id="boot-screen">
      <div class="boot-line">QLAB-7 SIMULATION INTERFACE</div>
      <div class="boot-line">YEAR 2157 — COHERENCE CRITICAL</div>
      <div class="boot-line boot-blink">INITIALIZING…</div>
    </div>
  `);
  playerInput.value = '';
  gameActive = false;
  updateStatusBar(null);
  statRoom.textContent = '◈ —';
  statTurn.textContent = 'TURN —/25';
  statObserver.textContent = 'OBSERVER: —';
  statInv.textContent = 'INV: —';
  statExits.textContent = 'EXITS: —';

  setLoading(true);

  try {
    const res = await fetch('/api/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: getApiKey(), story_id: storyId || selectedStory || 'qlab7' })
    });

    if (!res.ok) throw new Error('Server error ' + res.status);
    const data = await res.json();

    if (data.story) {
      const titleEl = document.querySelector('.terminal-title');
      if (titleEl) {
        titleEl.textContent = data.story.icon + ' ' + data.story.title;
        titleEl.style.color = data.story.color;
      }
    }
    updateStatusBar(data.state);
    updateNarrMode(data.narrative_mode);
    gameActive = true;
    setLoading(false);

    await appendEntry(null, data.narrative);
    enableInput();
  } catch (err) {
    setLoading(false);
    await appendEntry(null, 'QLAB-7 connection failed. ' + err.message);
  }
}

/* ═══════════════════════════════════════════════════════════
   PLAYER ACTION
   ═══════════════════════════════════════════════════════════ */

async function submitAction() {
  const raw = playerInput.value.trim();
  if (!raw || !gameActive || typewriterBusy) return;

  playerInput.value = '';
  disableInput();
  setLoading(true);
  appendDivider();

  try {
    const res = await fetch('/api/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: raw, api_key: getApiKey() })
    });

    if (!res.ok) throw new Error('Server error ' + res.status);
    const data = await res.json();

    updateStatusBar(data.state);
    updateNarrMode(data.narrative_mode);
    setLoading(false);

    const variant = data.status === 'win' ? 'win' : data.status === 'lose' ? 'lose' : null;
    await appendEntry(raw, data.narrative, variant);

    if (data.status === 'win' || data.status === 'lose') {
      gameActive = false;
      setTimeout(() => showEndOverlay(data.status, data.narrative), 600);
    } else {
      enableInput();
    }
  } catch (err) {
    setLoading(false);
    await appendEntry(raw, 'Something went wrong reaching QLAB-7. ' + err.message);
    enableInput();
  }
}

/* ── Input helpers ───────────────────────────────────────── */

function enableInput() {
  playerInput.disabled = false;
  sendBtn.disabled = false;
  playerInput.focus();
}

function disableInput() {
  playerInput.disabled = true;
  sendBtn.disabled = true;
}

/* ── Event bindings ──────────────────────────────────────── */

sendBtn.addEventListener('click', submitAction);

playerInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') submitAction();
});

/* ═══════════════════════════════════════════════════════════
   INIT — start game on page load
   ═══════════════════════════════════════════════════════════ */

window.addEventListener('DOMContentLoaded', () => {
  // Show a brief hint if no API key is set yet
  if (!getApiKey()) {
    setTimeout(() => {
      const hint = document.createElement('div');
      hint.style.cssText = `
        position: fixed; bottom: 80px; right: 20px;
        background: #0a0a10; border: 1px solid #2a5c30;
        color: #4a6a4e; font-family: var(--font); font-size: 11px;
        padding: 10px 14px; z-index: 400; letter-spacing: 0.05em;
        animation: fadeSlideIn 0.4s ease forwards;
      `;
      hint.innerHTML = '⚙ No API key set — <button onclick="document.getElementById(\'api-key-btn\').click();this.parentElement.remove()" style="background:none;border:none;color:#39ff84;font-family:inherit;font-size:inherit;cursor:pointer;letter-spacing:inherit;">configure now</button>';
      document.body.appendChild(hint);
      setTimeout(() => hint.remove(), 7000);
    }, 1200);
  }

  // Show story selection on load
  showStorySelect();
});
