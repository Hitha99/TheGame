"""
Build image URLs for the scene panel (Pollinations — no API key).
Prompts are derived from the current room and selected story only (not raw LLM text),
to keep URLs bounded and avoid leaking player input into a third-party service.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

POLLINATIONS = "https://image.pollinations.ai/prompt"

# On-disk pack: `static/scene_images/{story_id}__{room_id}__{status}.jpg` (see scripts/pregenerate_scene_images.py)
_SCENE_DIR = Path(__file__).resolve().parent / "static" / "scene_images"


def prebuilt_scene_dir() -> Path:
    return _SCENE_DIR


def scene_images_offline_only() -> bool:
    """If true, never fetch Pollinations — only disk (and in-process LRU) may serve bytes."""
    return os.environ.get("SCENE_IMAGES_OFFLINE_ONLY", "").strip().lower() in ("1", "true", "yes")


def scene_image_save_fetched_to_disk() -> bool:
    """If true, after a successful Pollinations fetch the server writes the JPEG into static/scene_images/."""
    return os.environ.get("SCENE_IMAGE_SAVE_FETCHED", "").strip().lower() in ("1", "true", "yes")


def prebuilt_scene_path(story_id: str, room_id: str, status: str) -> Path | None:
    """
    If a matching file exists under static/scene_images/, return it.
    Otherwise None (Flask will fall back to Pollinations).
    """
    st = status if status in ("win", "lose", "continue") else "continue"
    stem = f"{story_id}__{room_id}__{st}"
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        p = _SCENE_DIR / f"{stem}{ext}"
        if p.is_file():
            return p
    return None


def iter_pregenerate_tasks(game_data: dict, stories: list[dict]) -> list[tuple[str, str, str]]:
    """(story_id, room_id, status) tuples for a full offline image pack."""
    rooms = list((game_data.get("rooms") or {}).keys())
    out: list[tuple[str, str, str]] = []
    for s in stories:
        sid = s["id"]
        for rid in rooms:
            out.append((sid, rid, "continue"))
        for rid in rooms:
            out.append((sid, rid, "lose"))
        out.append((sid, "core", "win"))
    return out


def _stable_seed(room_id: str, story_id: str) -> int:
    h = hash(f"{story_id}:{room_id}") & 0x7FFFFFFF
    return h if h else 1


def build_scene_image_url(
    room_id: str,
    story: dict,
    game_data: dict,
    status: str = "continue",
) -> str | None:
    """
    Return a Pollinations image URL, or None if scene images are disabled server-side.
    """
    if os.environ.get("DISABLE_SCENE_IMAGES", "").strip().lower() in ("1", "true", "yes"):
        return None

    rooms = game_data.get("rooms") or {}
    room = rooms.get(room_id) or rooms.get("quantum_nexus", {})
    name = room.get("name", "Unknown chamber")

    # Shorter prompts = slightly faster upstream processing; still readable scenes.
    style = (story.get("tone") or "")[:90]
    world = (story.get("world_context") or "")[:90]
    story_title = story.get("title", "Adventure")

    if status == "win":
        core = (
            f"Cinematic digital painting, triumphant soft light, abstract sci-fi resolution, "
            f"no people, no text, no watermark. Theme: escape and closure. {story_title}."
        )
    elif status == "lose":
        core = (
            f"Cinematic digital painting, dark moody void, subtle dread, environment only, "
            f"no people, no text, no watermark. Theme: simulation failure. {story_title}."
        )
    else:
        desc = (room.get("description") or "")[:140]
        core = (
            f"Cinematic environment concept art, wide shot, no characters, no faces, no text, "
            f"no watermark. Location: {name}. {desc} Mood: {style}. {world}"
        )

    # Hard cap for URL length and provider limits
    prompt = core[:420]
    seed = _stable_seed(room_id, story.get("id", "qlab7"))
    w = max(256, min(1024, int(os.environ.get("SCENE_IMAGE_WIDTH", "512"))))
    h = max(256, min(1024, int(os.environ.get("SCENE_IMAGE_HEIGHT", "320"))))
    # "turbo" is much faster than default flux on the free image endpoint; override with SCENE_IMAGE_MODEL=flux for quality.
    model = (os.environ.get("SCENE_IMAGE_MODEL", "turbo") or "turbo").strip()
    q = (
        f"?width={w}&height={h}&seed={seed}&model={quote(model, safe='')}"
        "&nologo=true&enhance=false"
    )
    return f"{POLLINATIONS}/{quote(prompt, safe='')}{q}"
