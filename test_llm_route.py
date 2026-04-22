#!/usr/bin/env python3
"""
End-to-end LLM test of the perfect route.
Uses the TAMUS_AI_CHAT_API_KEY from .env (loaded via server).
Verifies narr_mode == 'ai' on every turn.
Retries on quantum_door collapse (40% chance).
"""
import sys
import requests

BASE = "http://127.0.0.1:5001"

PERFECT_ROUTE = [
    ("examine flickering console",        "examine"),
    ("go east",                           "go"),
    ("take mirror key",                   "take"),
    ("go west",                           "go"),
    ("examine quantum door",              "examine"),
    ("go north",                          "go"),
    ("take prism shard",                  "take"),
    ("go west",                           "go"),
    ("I believe the bridge is solid",     "believe"),
    ("go across",                         "go"),
    ("take quantum key",                  "take"),
    ("go north",                          "go"),
    ("use quantum key on core stabilizer","use"),
]

CLOSED_DOOR_INDICATORS = [
    "solidified into a closed", "sealed by its own observation",
    "closed state", "door has made its choice", "path is sealed",
]

ISSUES = []  # accumulated problems across the run


def start(session, story_id="qlab7"):
    r = session.post(f"{BASE}/api/start", json={"story_id": story_id})
    r.raise_for_status()
    return r.json()


def action(session, text):
    r = session.post(f"{BASE}/api/action", json={"action": text})
    r.raise_for_status()
    return r.json()


def check_mode(step, cmd, mode, expected="ai"):
    if mode != expected:
        msg = f"  ⚠  Step {step} '{cmd}': narr_mode={mode!r} (expected {expected!r})"
        print(msg)
        ISSUES.append(msg)


def run_once(attempt, story_id):
    session = requests.Session()
    print(f"\n{'='*62}")
    print(f"  Attempt {attempt}  |  story: {story_id}")
    print(f"{'='*62}")

    data = start(session, story_id)
    mode = data.get("narrative_mode", "?")
    print(f"[START] mode={mode}  room={data['state']['room_id']}")
    print(f"        narrative: {data['narrative'][:160]}…\n")
    check_mode("start", "start", mode)

    for step_num, (cmd, verb) in enumerate(PERFECT_ROUTE, start=1):
        data = action(session, cmd)
        narr   = data["narrative"]
        status = data["status"]
        mode   = data.get("narrative_mode", "?")
        state  = data["state"]

        print(f"[{step_num:02d}] > {cmd}")
        print(f"      mode={mode}  status={status}  room={state['room_id']}")
        print(f"      inv={state.get('inventory', [])}")
        print(f"      narrative: {narr[:180]}…")
        print()

        check_mode(step_num, cmd, mode)

        # Detect closed door after examining it
        if step_num == 5:
            n = narr.lower()
            if any(p in n for p in CLOSED_DOOR_INDICATORS):
                print("  ⚠  Door collapsed CLOSED — retrying.\n")
                return "door_closed"

        # Detect movement failure (still in same room)
        if step_num == 6 and state["room_id"] == "quantum_nexus":
            print("  ⚠  go north failed — door is closed. Retrying.\n")
            return "door_closed"

        if status == "win":
            print(f"  🎉  WIN at step {step_num}")
            return "win"

        if status == "lose":
            print(f"  ❌  LOSE at step {step_num} — {data.get('message')}")
            ISSUES.append(f"Unexpected LOSE at step {step_num}: {data.get('message')}")
            return "lose"

    print("  ✗  Route finished but no win.")
    ISSUES.append("Route complete without win status")
    return "no_win"


def main():
    max_retries = 15

    for story_id in ["qlab7", "glass_archive", "sector_null"]:
        print(f"\n\n{'#'*62}")
        print(f"  STORY: {story_id}")
        print(f"{'#'*62}")

        for attempt in range(1, max_retries + 1):
            result = run_once(attempt, story_id)
            if result == "win":
                print(f"\n✅  '{story_id}' PASSED — {attempt} attempt(s).")
                break
            elif result == "door_closed":
                continue
            else:
                print(f"\n❌  '{story_id}' FAILED: {result}")
                break
        else:
            ISSUES.append(f"'{story_id}' never won in {max_retries} attempts")

    print(f"\n{'='*62}")
    if ISSUES:
        print(f"  ISSUES FOUND ({len(ISSUES)}):")
        for i in ISSUES:
            print(f"    {i}")
        print(f"{'='*62}")
        sys.exit(1)
    else:
        print("  ALL STORIES PASSED — no issues detected.")
        print(f"{'='*62}\n")


if __name__ == "__main__":
    main()
