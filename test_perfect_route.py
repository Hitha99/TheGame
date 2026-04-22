#!/usr/bin/env python3
"""
End-to-end test of the perfect route (no API key, fallback narration).
Retries up to 10 times because `examine quantum door` is 40% chance closed.
"""
import sys
import requests

BASE = "http://127.0.0.1:5001"

PERFECT_ROUTE = [
    ("examine flickering console",        "examine"),
    ("go east",                           "go"),
    ("take mirror key",                   "take"),
    ("go west",                           "go"),
    ("examine quantum door",              "examine"),   # random: open or closed
    ("go north",                          "go"),        # only works if door open
    ("take prism shard",                  "take"),
    ("go west",                           "go"),
    ("I believe the bridge is solid",     "believe"),
    ("go across",                         "go"),
    ("take quantum key",                  "take"),
    ("go north",                          "go"),
    ("use quantum key on core stabilizer","use"),       # should WIN
]

CLOSED_DOOR_INDICATORS = [
    "solidified into a closed",
    "sealed by its own observation",
    "closed state",
    "cannot go",
    "door has made its choice",
    "closed",
]


def make_session():
    return requests.Session()


def start(session, story_id="qlab7"):
    r = session.post(f"{BASE}/api/start", json={"story_id": story_id})
    r.raise_for_status()
    return r.json()


def action(session, text):
    r = session.post(f"{BASE}/api/action", json={"action": text})
    r.raise_for_status()
    return r.json()


def door_is_closed(narrative, status_data):
    """Heuristic: door collapsed to closed if narrative says so or go-north is blocked."""
    n = narrative.lower()
    return any(phrase in n for phrase in CLOSED_DOOR_INDICATORS)


def run_once(attempt, story_id="qlab7"):
    session = make_session()
    print(f"\n{'='*60}")
    print(f"  ATTEMPT {attempt}  —  story: {story_id}")
    print(f"{'='*60}")

    data = start(session, story_id)
    print(f"[START] status={data['status']}  narr_mode={data.get('narrative_mode')}")
    print(f"        room={data['state']['room_id']}")
    print(f"        narrative: {data['narrative'][:120]}…\n")

    for step_num, (cmd, verb) in enumerate(PERFECT_ROUTE, start=1):
        data = action(session, cmd)
        narr = data["narrative"]
        status = data["status"]
        mode = data.get("narrative_mode", "?")
        state = data["state"]

        print(f"[{step_num:02d}] > {cmd}")
        print(f"      status={status}  mode={mode}  room={state['room_id']}")
        print(f"      inv={state.get('inventory', [])}")
        print(f"      narrative: {narr[:140]}…")
        print()

        # After examining the door, check if it closed
        if step_num == 5 and verb == "examine":
            if door_is_closed(narr, state):
                print("  ⚠  Door collapsed CLOSED — restarting this attempt.")
                return "door_closed"

        # After go north (step 6), if we're still in quantum_nexus, door is closed
        if step_num == 6 and verb == "go":
            if state["room_id"] == "quantum_nexus":
                print("  ⚠  go north failed (still in quantum_nexus) — door closed.")
                return "door_closed"

        if status == "win":
            print("  🎉  WIN detected at step", step_num)
            return "win"

        if status == "lose":
            print("  ❌  LOSE detected at step", step_num)
            print("      message:", data.get("message"))
            return "lose"

    print("  ✗  Route complete but no win status returned.")
    return "no_win"


def main():
    max_attempts = 15
    wins = 0
    losses = 0
    door_closes = 0

    # Test all three stories
    for story_id in ["qlab7", "glass_archive", "sector_null"]:
        print(f"\n\n{'#'*60}")
        print(f"  STORY: {story_id}")
        print(f"{'#'*60}")
        for attempt in range(1, max_attempts + 1):
            result = run_once(attempt, story_id)
            if result == "win":
                wins += 1
                print(f"\n✅ Story '{story_id}' passed in {attempt} attempt(s).")
                break
            elif result == "door_closed":
                door_closes += 1
                print(f"   Retrying…\n")
            elif result == "lose":
                losses += 1
                print(f"\n❌ Story '{story_id}' lost unexpectedly.")
                sys.exit(1)
            else:
                print(f"\n❌ Story '{story_id}': unexpected result '{result}'")
                sys.exit(1)
        else:
            print(f"\n❌ Story '{story_id}' never got an open door after {max_attempts} attempts.")
            sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  ALL STORIES PASSED")
    print(f"  wins={wins}  losses={losses}  door_retries={door_closes}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
