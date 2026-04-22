"""Generate architecture diagram for QLAB-7 Quantum Text Adventure."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import matplotlib.patheffects as pe

fig, ax = plt.subplots(figsize=(14, 9))
fig.patch.set_facecolor('#050508')
ax.set_facecolor('#050508')
ax.set_xlim(0, 14)
ax.set_ylim(0, 9)
ax.axis('off')

# ── Palette ───────────────────────────────────────────────
C_BG       = '#050508'
C_BOX_BG   = '#0a0a14'
C_GREEN    = '#39ff84'
C_GREEN_D  = '#1a6640'
C_AMBER    = '#ffb347'
C_AMBER_D  = '#7a4d10'
C_BLUE     = '#4a9eff'
C_BLUE_D   = '#1a3a6a'
C_PURPLE   = '#b47aff'
C_PURPLE_D = '#3a1a6a'
C_EDGE     = '#2a5c30'
C_TEXT     = '#c8e6c9'
C_DIM      = '#4a6a4e'


def box(ax, x, y, w, h, label, sublabel='', color=C_GREEN, bg=C_BOX_BG,
        border=None, fontsize=11):
    border = border or color
    rect = FancyBboxPatch(
        (x - w/2, y - h/2), w, h,
        boxstyle='round,pad=0.09', linewidth=1.6,
        edgecolor=border, facecolor=bg, zorder=3
    )
    ax.add_patch(rect)
    ax.text(x, y + (0.13 if sublabel else 0), label,
            ha='center', va='center', fontsize=fontsize, fontweight='bold',
            color=color, fontfamily='monospace', zorder=4)
    if sublabel:
        ax.text(x, y - 0.25, sublabel,
                ha='center', va='center', fontsize=8,
                color=C_DIM, fontfamily='monospace', zorder=4)


def arrow(ax, x1, y1, x2, y2, label='', color=C_EDGE, label_dx=0.1, label_dy=0):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=1.6,
                                connectionstyle='arc3,rad=0.0'), zorder=2)
    if label:
        mx = (x1 + x2) / 2 + label_dx
        my = (y1 + y2) / 2 + label_dy
        ax.text(mx, my, label, ha='left', va='center', fontsize=7.5,
                color=C_DIM, fontfamily='monospace', zorder=5)


# ── Title ─────────────────────────────────────────────────
ax.text(7, 8.58,
        'QLAB-7  //  QUANTUM TEXT ADVENTURE — SYSTEM ARCHITECTURE',
        ha='center', va='center', fontsize=13, fontweight='bold',
        color=C_GREEN, fontfamily='monospace',
        path_effects=[pe.withStroke(linewidth=7, foreground=C_BG)])

# ── Band backgrounds ──────────────────────────────────────
for (bx, by, bw, bh, bc, bt) in [
    (7, 7.72, 13.2, 1.2,  '#0d0d08', 'BROWSER LAYER'),
    (7, 6.35, 13.2, 1.5,  '#080810', 'FRONTEND LAYER'),
    (7, 5.0,  13.2, 0.9,  '#080e08', 'SERVER LAYER'),
    (7, 3.72, 13.2, 1.35, '#0c0812', 'MODULE LAYER'),
    (7, 2.05, 13.2, 0.95, '#0e0900', 'EXTERNAL API'),
]:
    ax.add_patch(FancyBboxPatch(
        (bx - bw/2, by - bh/2), bw, bh,
        boxstyle='round,pad=0.06', linewidth=0.8,
        edgecolor='#1a1a2a', facecolor=bc, zorder=1
    ))
    ax.text(0.52, by, bt, ha='center', va='center', fontsize=6.5,
            color='#2a2a3a', fontfamily='monospace', fontweight='bold',
            rotation=90)

# ── Nodes ─────────────────────────────────────────────────
# Player
box(ax, 7, 7.72, 2.4, 0.75, '[ PLAYER ]', 'browser / keyboard',
    color=C_AMBER, bg='#130d00', border=C_AMBER_D, fontsize=12)

# localStorage
box(ax, 11.6, 7.72, 2.1, 0.72, 'localStorage',
    'api_key (browser)',
    color=C_DIM, bg='#080808', border='#1e2e1e', fontsize=9)

# Frontend
box(ax, 3.5,  6.35, 2.3, 0.78, 'index.html', 'page shell · layout',
    color=C_BLUE, bg='#060618', border=C_BLUE_D)
box(ax, 7.0,  6.35, 2.3, 0.78, 'game.js',    'input · typewriter · overlay',
    color=C_BLUE, bg='#060618', border=C_BLUE_D)
box(ax, 10.5, 6.35, 2.3, 0.78, 'style.css',  'terminal UI · scanlines',
    color=C_BLUE, bg='#060618', border=C_BLUE_D)

# Flask
box(ax, 7, 5.0, 3.2, 0.78, 'app.py  (Flask)',
    '/api/start  ·  /api/action  ·  /api/reset',
    color=C_GREEN, bg='#060e06', border=C_GREEN_D, fontsize=11)

# Python modules
box(ax, 3.5,  3.72, 3.0, 0.82, 'quantum_rules.py',
    'parse · validate · effects · win/lose',
    color=C_PURPLE, bg='#0a0818', border=C_PURPLE_D, fontsize=10)
box(ax, 7.0,  3.72, 2.2, 0.82, 'narrative.py',
    'prompts · history · fallback',
    color=C_PURPLE, bg='#0a0818', border=C_PURPLE_D, fontsize=10)
box(ax, 10.5, 3.72, 2.8, 0.82, 'game_data.json',
    '6 rooms · 10 objects',
    color=C_PURPLE, bg='#0a0818', border=C_PURPLE_D, fontsize=10)

# TAMU API
box(ax, 7, 2.05, 3.8, 0.82, 'TAMU AI CHAT API',
    'chat-api.tamu.ai  ·  gemini-2.0-flash-lite',
    color=C_AMBER, bg='#130d00', border=C_AMBER_D, fontsize=10)

# ── Arrows ────────────────────────────────────────────────
# Player ↔ game.js
arrow(ax, 6.1, 7.35, 6.6, 6.75, 'action text', label_dx=0.08)
arrow(ax, 7.4, 6.75, 7.9, 7.35, '→ narrative', label_dx=0.08)

# localStorage ↔ game.js
arrow(ax, 10.55, 7.72, 8.16, 7.72, '', color='#2a3a2a')
ax.text(9.3, 7.83, 'api_key', ha='center', fontsize=7.5,
        color=C_DIM, fontfamily='monospace')

# game.js ↔ Flask
arrow(ax, 7.0, 5.96, 7.0, 5.40, 'POST /api/action', label_dx=0.1)
arrow(ax, 7.4, 5.40, 7.4, 5.96, '← response JSON', label_dx=0.1)

# Flask → modules
arrow(ax, 5.5, 4.62, 4.5, 4.14)
arrow(ax, 7.0, 4.62, 7.0, 4.14)
arrow(ax, 8.5, 4.62, 9.6, 4.14)

# narrative.py ↔ TAMU API
arrow(ax, 6.7, 3.30, 6.7, 2.47, 'system+turn prompt', color=C_AMBER_D,
      label_dx=0.1)
arrow(ax, 7.3, 2.47, 7.3, 3.30, '← 2-4 sentence prose', color=C_AMBER_D,
      label_dx=0.1)

# ── Legend ────────────────────────────────────────────────
legend = [
    (C_AMBER,  'Player / External'),
    (C_BLUE,   'Frontend (Browser)'),
    (C_GREEN,  'Flask Server'),
    (C_PURPLE, 'Python Modules'),
]
for i, (col, lbl) in enumerate(legend):
    lx = 1.0 + i * 3.1
    ax.add_patch(FancyBboxPatch((lx, 0.38), 0.32, 0.32,
        boxstyle='round,pad=0.04', facecolor='#0a0a14',
        edgecolor=col, linewidth=1.5, zorder=3))
    ax.text(lx + 0.46, 0.54, lbl, va='center', fontsize=8.5,
            color=C_DIM, fontfamily='monospace')

# ── Save ──────────────────────────────────────────────────
import pathlib
out = str(pathlib.Path(__file__).parent / 'architecture.png')
fig.tight_layout(pad=0.2)
fig.savefig(out, dpi=180, bbox_inches='tight', facecolor=C_BG)
print(f'Saved: {out}')
