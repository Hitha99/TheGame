#!/usr/bin/env python3
"""
Download every scene image from Pollinations into static/scene_images/.

Naming: {story_id}__{room_id}__{status}.jpg
  e.g. qlab7__quantum_nexus__continue.jpg

The Flask route /api/scene-image serves these files instantly when present.

Usage (from TheGame folder, with venv activated):
  python scripts/pregenerate_scene_images.py

Options:
  --force     Overwrite existing files
  --delay N   Seconds between requests (default 2.0)
  --dry-run   Print tasks only, do not download
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scene_image import (  # noqa: E402
    build_scene_image_url,
    iter_pregenerate_tasks,
    prebuilt_scene_dir,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-download scene images into static/scene_images/")
    parser.add_argument("--force", action="store_true", help="Overwrite existing JPEGs")
    parser.add_argument("--delay", type=float, default=2.0, help="Pause between HTTP requests (seconds)")
    parser.add_argument("--dry-run", action="store_true", help="List work only")
    args = parser.parse_args()

    game_data = json.loads((ROOT / "game_data.json").read_text(encoding="utf-8"))
    stories = json.loads((ROOT / "stories.json").read_text(encoding="utf-8"))
    stories_by_id = {s["id"]: s for s in stories}

    out_dir = prebuilt_scene_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    tasks = iter_pregenerate_tasks(game_data, stories)
    print(f"Tasks: {len(tasks)} images → {out_dir}")

    session = requests.Session()
    session.headers["User-Agent"] = "QuantumGame-scene-pregen/1.0"

    failed = 0
    skipped = 0
    ok = 0

    for i, (story_id, room_id, status) in enumerate(tasks):
        dest = out_dir / f"{story_id}__{room_id}__{status}.jpg"
        if dest.is_file() and not args.force:
            print(f"[{i + 1}/{len(tasks)}] skip (exists): {dest.name}")
            skipped += 1
            continue

        story = stories_by_id[story_id]
        url = build_scene_image_url(room_id, story, game_data, status)
        if not url:
            print(f"[{i + 1}/{len(tasks)}] skip (DISABLE_SCENE_IMAGES): {dest.name}")
            skipped += 1
            continue

        if args.dry_run:
            print(f"[dry-run] would fetch → {dest.name}")
            continue

        print(f"[{i + 1}/{len(tasks)}] GET {dest.name} …")
        try:
            r = session.get(url, timeout=240)
        except requests.RequestException as e:
            print(f"  ERROR: {e}")
            failed += 1
            continue

        if r.status_code != 200 or not r.content or len(r.content) < 200:
            print(f"  ERROR: HTTP {r.status_code}, len={len(r.content or b'')}")
            failed += 1
            continue

        if r.content[:1] in (b"{", b"<"):
            print("  ERROR: response looks like JSON/HTML, not an image")
            failed += 1
            continue

        dest.write_bytes(r.content)
        print(f"  wrote {len(r.content)} bytes")
        ok += 1

        if args.delay > 0 and i < len(tasks) - 1:
            time.sleep(args.delay)

    print(f"Done. ok={ok} skipped={skipped} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
