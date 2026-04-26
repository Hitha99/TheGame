/**
 * map.js — Mini-map for Quantum Nexus
 *
 * Schematic node graph:
 *   - 6 rooms as dots, edges = valid exits
 *   - Current room glows in scenario color
 *   - Visited rooms filled, unvisited hidden (fog of war)
 *   - Edges to unvisited rooms revealed only after the connecting room is visited
 *
 * Sits above the visualizer panel in a 30/70 vertical split.
 *
 * Self-contained — reads current room from status bar, scenario from
 * window.selectedStory, persists "visited" set in localStorage.
 */

'use strict';

(() => {
  /* ── Room graph (mirrors app.py ROOM_EXITS) ──────────────── */
  const ROOMS = {
    quantum_nexus:       { x: 0.50, y: 0.85 },
    void_corridor:       { x: 0.20, y: 0.55 },
    entanglement_lab:    { x: 0.78, y: 0.55 },
    superposition_vault: { x: 0.20, y: 0.25 },
    observer_chamber:    { x: 0.78, y: 0.25 },
    core:                { x: 0.50, y: 0.10 },
  };

  // Edges (undirected, so just one entry per pair)
  const EDGES = [
    ['quantum_nexus',     'void_corridor'],
    ['quantum_nexus',     'entanglement_lab'],
    ['void_corridor',     'superposition_vault'],
    ['entanglement_lab',  'observer_chamber'],
    ['superposition_vault','observer_chamber'],   // "across"
    ['observer_chamber',  'core'],
  ];

  // Per-scenario display names — matches stories.json room_aliases
  const ROOM_NAMES = {
    qlab7: {
      quantum_nexus: 'NEXUS',
      void_corridor: 'CORRIDOR',
      entanglement_lab: 'LAB',
      superposition_vault: 'VAULT',
      observer_chamber: 'OBSERVER',
      core: 'CORE',
    },
    glass_archive: {
      quantum_nexus: 'ROOFTOP',
      void_corridor: 'SUBLEVEL',
      entanglement_lab: 'DATA VAULT',
      superposition_vault: 'MAINT BAY',
      observer_chamber: 'EXEC FLOOR',
      core: 'SERVER CORE',
    },
    sector_null: {
      quantum_nexus: 'SURFACE',
      void_corridor: 'CORRIDOR',
      entanglement_lab: 'RELAY BAY',
      superposition_vault: 'BUNKER',
      observer_chamber: 'TOWER BASE',
      core: 'TOWER CORE',
    },
  };

  // Reverse lookup: aliased room name → room id (per scenario)
  // Built lazily by reading window.STORY_DATA if available, falls back to
  // matching by ROOM_NAMES short names (case-insensitive substring match).
  const FULL_ROOM_NAMES = {
    qlab7: {
      quantum_nexus: 'The Quantum Nexus',
      void_corridor: 'The Void Corridor',
      entanglement_lab: 'The Entanglement Laboratory',
      superposition_vault: 'The Superposition Vault',
      observer_chamber: "The Observer's Chamber",
      core: 'The Core Singularity',
    },
    glass_archive: {
      quantum_nexus: 'Rooftop Access',
      void_corridor: 'Service Sublevel',
      entanglement_lab: 'Data Vault',
      superposition_vault: 'Sealed Maintenance Bay',
      observer_chamber: 'Executive Floor',
      core: 'Server Core',
    },
    sector_null: {
      quantum_nexus: 'Surface Pad',
      void_corridor: 'Buried Corridor',
      entanglement_lab: 'Relay Bay',
      superposition_vault: 'Sealed Bunker',
      observer_chamber: 'Tower Base',
      core: 'Relay Tower Core',
    },
  };

  /* ── Theme colors (mirror visuals.js) ────────────────────── */
  const THEME_COLORS = {
    qlab7:         { r: 57,  g: 255, b: 132 },
    glass_archive: { r: 255, g: 95,  b: 190 },
    sector_null:   { r: 255, g: 179, b: 71  },
  };

  /* ── State ───────────────────────────────────────────────── */
  let currentStoryId = null;
  let currentRoomId  = null;
  let visited = new Set();

  function lsKey(storyId) { return 'qn_visited_' + (storyId || 'unknown'); }
  function loadVisited(storyId) {
    try {
      const raw = localStorage.getItem(lsKey(storyId));
      visited = new Set(raw ? JSON.parse(raw) : []);
    } catch { visited = new Set(); }
  }
  function saveVisited(storyId) {
    try { localStorage.setItem(lsKey(storyId), JSON.stringify([...visited])); }
    catch {}
  }
  function resetVisited(storyId) {
    visited = new Set();
    try { localStorage.removeItem(lsKey(storyId)); } catch {}
  }

  /* ── CSS ─────────────────────────────────────────────────── */
  function injectStyles() {
    if (document.getElementById('map-styles')) return;
    const css = `
      .map-panel {
        flex: 0 0 30%;
        min-height: 0;
        border-bottom: 1px solid var(--border-hi);
        display: flex;
        flex-direction: column;
        background: var(--bg-panel);
      }
      .map-header {
        padding: 8px 18px;
        font-size: 11px; letter-spacing: 0.1em;
        color: var(--text-dim);
        border-bottom: 1px solid var(--border-hi);
        display: flex; justify-content: space-between; align-items: center;
        flex-shrink: 0;
      }
      .map-header .map-title { color: var(--green-dim); transition: color 0.6s; }
      .map-header .map-progress { font-size: 10px; opacity: 0.7; }
      .map-canvas-wrap { flex: 1 1 auto; position: relative; min-height: 0; }
      #map-canvas { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }

      /* Make room above visualizer */
      .viz-panel { flex: 1 1 70%; }

      @media (max-width: 900px) {
        .map-panel { flex: 0 0 25%; }
        .viz-panel { flex: 1 1 75%; }
      }
    `;
    const tag = document.createElement('style');
    tag.id = 'map-styles';
    tag.textContent = css;
    document.head.appendChild(tag);
  }

  /* ── DOM injection ───────────────────────────────────────── */
  function injectPanel() {
    const vizPanel = document.querySelector('.viz-panel');
    if (!vizPanel) return null;

    const panel = document.createElement('aside');
    panel.className = 'map-panel';
    panel.innerHTML = `
      <div class="map-header">
        <span class="map-title" id="map-title">◇ TOPOLOGY MAP</span>
        <span class="map-progress" id="map-progress">0 / 6 explored</span>
      </div>
      <div class="map-canvas-wrap"><canvas id="map-canvas"></canvas></div>
    `;
    vizPanel.parentNode.insertBefore(panel, vizPanel);
    return panel;
  }

  /* ── Drawing ─────────────────────────────────────────────── */
  function startEngine() {
    const canvas    = document.getElementById('map-canvas');
    const ctx       = canvas.getContext('2d', { alpha: true });
    const titleEl   = document.getElementById('map-title');
    const progressEl = document.getElementById('map-progress');

    let w = 0, h = 0;
    function resize() {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      w = rect.width;
      h = rect.height;
      canvas.width  = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();
    window.addEventListener('resize', resize);

    let lastTime = performance.now();
    let frameNo = 0;
    let running = true;
    document.addEventListener('visibilitychange', () => {
      running = !document.hidden;
      if (running) lastTime = performance.now();
    });

    function frame(now) {
      requestAnimationFrame(frame);
      if (!running) return;
      const dt = Math.min(now - lastTime, 50);
      lastTime = now;
      frameNo++;

      const color = THEME_COLORS[currentStoryId] || THEME_COLORS.qlab7;
      const dimColor = `rgba(${color.r},${color.g},${color.b},0.18)`;

      // Background fade
      ctx.fillStyle = 'rgba(10,10,16,0.7)';
      ctx.fillRect(0, 0, w, h);

      // Padding from edges
      const padX = 30, padY = 22;
      const usableW = Math.max(20, w - padX * 2);
      const usableH = Math.max(20, h - padY * 2);

      function pos(roomId) {
        const r = ROOMS[roomId];
        return { x: padX + r.x * usableW, y: padY + r.y * usableH };
      }

      // ── Draw edges first (so dots overlap them) ──
      // An edge is "visible" only if at least one of its endpoints is visited.
      // If both ends are visited, draw bright; if only one, draw dim hint.
      ctx.lineCap = 'round';
      for (const [a, b] of EDGES) {
        const va = visited.has(a);
        const vb = visited.has(b);
        if (!va && !vb) continue;
        const pa = pos(a), pb = pos(b);
        if (va && vb) {
          ctx.strokeStyle = `rgba(${color.r},${color.g},${color.b},0.55)`;
          ctx.lineWidth = 1.2;
        } else {
          ctx.setLineDash([3, 4]);
          ctx.strokeStyle = dimColor;
          ctx.lineWidth = 1;
        }
        ctx.beginPath();
        ctx.moveTo(pa.x, pa.y);
        ctx.lineTo(pb.x, pb.y);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // ── Draw rooms ──
      // Visited rooms: filled circle + label
      // Unvisited but connected to visited: dim outline circle, "?" label
      // Otherwise: not drawn at all (fog of war)
      const labels = ROOM_NAMES[currentStoryId] || ROOM_NAMES.qlab7;
      const candidateRooms = new Set();
      visited.forEach(rid => {
        candidateRooms.add(rid);
        for (const [a, b] of EDGES) {
          if (a === rid) candidateRooms.add(b);
          if (b === rid) candidateRooms.add(a);
        }
      });
      // Always include current room
      if (currentRoomId) candidateRooms.add(currentRoomId);

      for (const rid of candidateRooms) {
        const p = pos(rid);
        const isCurrent = (rid === currentRoomId);
        const isVisited = visited.has(rid);

        // Outer glow ring on current room
        if (isCurrent) {
          const pulse = 1 + Math.sin(now * 0.005) * 0.25;
          const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, 18 * pulse);
          grad.addColorStop(0, `rgba(${color.r},${color.g},${color.b},0.55)`);
          grad.addColorStop(1, `rgba(${color.r},${color.g},${color.b},0)`);
          ctx.fillStyle = grad;
          ctx.beginPath();
          ctx.arc(p.x, p.y, 18 * pulse, 0, Math.PI * 2);
          ctx.fill();
        }

        // Dot
        ctx.beginPath();
        ctx.arc(p.x, p.y, isCurrent ? 5 : 4, 0, Math.PI * 2);
        if (isVisited || isCurrent) {
          ctx.fillStyle = `rgb(${color.r},${color.g},${color.b})`;
          ctx.fill();
        } else {
          ctx.strokeStyle = dimColor;
          ctx.lineWidth = 1.2;
          ctx.stroke();
        }

        // Label
        ctx.font = '9px JetBrains Mono, monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillStyle = isCurrent
          ? `rgb(${color.r},${color.g},${color.b})`
          : isVisited
            ? `rgba(${color.r},${color.g},${color.b},0.7)`
            : `rgba(${color.r},${color.g},${color.b},0.3)`;
        const label = isVisited || isCurrent ? labels[rid] || '???' : '???';
        ctx.fillText(label, p.x, p.y + 8);
      }

      // Update header
      if (frameNo % 15 === 0) {
        if (titleEl) titleEl.style.color = `rgb(${color.r},${color.g},${color.b})`;
        if (progressEl) progressEl.textContent = `${visited.size} / 6 explored`;
      }
    }
    requestAnimationFrame(frame);
  }

  /* ── Read current room from status bar ───────────────────── */
  function detectCurrentRoom() {
    const roomEl = document.getElementById('stat-room');
    if (!roomEl) return null;
    // Strip leading "◈ " icon + spaces
    const text = roomEl.textContent.replace(/^[^A-Za-z]+/, '').trim();
    if (!text || text === '—') return null;

    const storyId = currentStoryId || 'qlab7';
    const namesForStory = FULL_ROOM_NAMES[storyId] || FULL_ROOM_NAMES.qlab7;

    // Try exact match first
    for (const [rid, name] of Object.entries(namesForStory)) {
      if (name.toLowerCase() === text.toLowerCase()) return rid;
    }
    // Substring fallback (handles minor naming differences)
    for (const [rid, name] of Object.entries(namesForStory)) {
      if (text.toLowerCase().includes(name.toLowerCase().split(' ').pop())) return rid;
    }
    // Last fallback: try all stories
    for (const story of Object.values(FULL_ROOM_NAMES)) {
      for (const [rid, name] of Object.entries(story)) {
        if (name.toLowerCase() === text.toLowerCase()) return rid;
      }
    }
    return null;
  }

  function detectStoryId() {
    return (typeof window.selectedStory !== 'undefined') ? window.selectedStory : null;
  }

  /* ── Watcher ─────────────────────────────────────────────── */
  function watchState() {
    function check() {
      const storyId = detectStoryId();
      if (storyId !== currentStoryId) {
        currentStoryId = storyId;
        loadVisited(storyId);
      }
      const rid = detectCurrentRoom();
      if (rid && rid !== currentRoomId) {
        currentRoomId = rid;
        if (!visited.has(rid)) {
          visited.add(rid);
          saveVisited(currentStoryId);
        }
      }
      // Detect restart — if status bar shows "—" again and we had a current room,
      // wipe visited so the map resets for a new run.
      const roomEl = document.getElementById('stat-room');
      if (roomEl && roomEl.textContent.trim() === '◈ —' && currentRoomId !== null) {
        currentRoomId = null;
        resetVisited(currentStoryId);
      }
    }

    // Initial
    currentStoryId = detectStoryId();
    loadVisited(currentStoryId);
    check();

    // Watch status bar mutations + poll fallback
    const target = document.getElementById('status-bar');
    if (target) {
      const mo = new MutationObserver(check);
      mo.observe(target, { subtree: true, childList: true, characterData: true, attributes: true });
    }
    setInterval(check, 700);
  }

  /* ── Init ────────────────────────────────────────────────── */
  function init() {
    // Wait for the visualizer to inject .viz-panel first
    function tryInject() {
      if (!document.querySelector('.viz-panel')) {
        return setTimeout(tryInject, 50);
      }
      injectStyles();
      const panel = injectPanel();
      if (!panel) return;
      requestAnimationFrame(() => { startEngine(); watchState(); });
    }
    tryInject();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
