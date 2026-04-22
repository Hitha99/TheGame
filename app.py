"""
app.py
======
Flask backend for The Quantum Text Adventure.

Routes:
    GET  /              → serve index.html
    POST /api/start     → initialize game state, return opening narrative
    POST /api/action    → process one player turn, return narrative + state
    POST /api/reset     → clear session (alias for start without returning narrative)
"""

import json
import copy
import os
from pathlib import Path

from flask import Flask, render_template, request, session, jsonify
from dotenv import load_dotenv

from quantum_rules import (
    auto_update_state,
    parse_intent,
    is_valid_action,
    apply_quantum_effect,
    check_entanglement_cascade,
    evaluate_win_loss,
    get_quantum_state_summary,
    ValidationResult,
)
from narrative import generate_narrative, build_opening_narrative

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "qlab7-secret-do-not-use-in-prod")

# Load static game data once at startup
GAME_DATA_PATH = Path(__file__).parent / "game_data.json"
with open(GAME_DATA_PATH, "r") as f:
    GAME_DATA = json.load(f)

STORIES_PATH = Path(__file__).parent / "stories.json"
with open(STORIES_PATH, "r") as f:
    STORIES = json.load(f)
STORIES_BY_ID = {s["id"]: s for s in STORIES}


# ─── Room adjacency (movement map) ────────────────────────────────────────────
# Maps (current_room, direction) → destination_room_id
# Blocked exits are still listed here; quantum_rules.is_valid_action enforces
# the conditions. If valid, we perform the move.
ROOM_EXITS: dict[tuple[str, str], str] = {
    ("quantum_nexus",     "north"):  "void_corridor",
    ("quantum_nexus",     "east"):   "entanglement_lab",
    ("void_corridor",     "south"):  "quantum_nexus",
    ("void_corridor",     "west"):   "superposition_vault",
    ("entanglement_lab",  "west"):   "quantum_nexus",
    ("entanglement_lab",  "north"):  "observer_chamber",
    ("superposition_vault", "east"): "void_corridor",
    ("superposition_vault", "across"): "observer_chamber",
    ("observer_chamber",  "south"):  "entanglement_lab",
    ("observer_chamber",  "north"):  "core",
    ("core",              "south"):  "observer_chamber",
}


def _initial_game_state() -> dict:
    """Return a fresh game state dict."""
    obj_states = {oid: obj["initial_state"] for oid, obj in GAME_DATA["objects"].items()}
    return {
        "current_room": "quantum_nexus",
        "inventory": [],
        "turn": 0,
        "object_states": obj_states,
        "quantum_events_log": [],
    }


def _apply_movement(intent, game_state: dict) -> dict:
    """
    If the intent is 'go' and the direction is valid, move the player.
    Should only be called after is_valid_action() returns True.
    """
    if intent.verb != "go":
        return game_state
    direction = intent.object_id
    destination = ROOM_EXITS.get((game_state["current_room"], direction))
    if destination:
        new_state = copy.deepcopy(game_state)
        new_state["current_room"] = destination
        return new_state
    return game_state


def _get_api_key() -> str:
    """Extract API key from request body (browser localStorage), else env var."""
    body = request.get_json(silent=True) or {}
    return body.get("api_key", "") or os.environ.get("TAMUS_AI_CHAT_API_KEY", "")


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/stories", methods=["GET"])
def get_stories():
    """Return the list of available stories for the selection screen."""
    return jsonify([
        {
            "id":       s["id"],
            "title":    s["title"],
            "subtitle": s["subtitle"],
            "tagline":  s["tagline"],
            "color":    s["color"],
            "icon":     s["icon"],
        }
        for s in STORIES
    ])


@app.route("/api/start", methods=["POST"])
def start_game():
    """Initialize a new game session and return the opening narrative."""
    body     = request.get_json(silent=True) or {}
    story_id = body.get("story_id", "qlab7")
    story    = STORIES_BY_ID.get(story_id, STORIES_BY_ID["qlab7"])

    state = _initial_game_state()
    session["game_state"] = state
    session["conversation_history"] = []
    session["story_id"] = story["id"]

    api_key = _get_api_key()
    summary = get_quantum_state_summary(state)
    narrative, narr_mode = build_opening_narrative(
        state, GAME_DATA, summary, story=story, api_key=api_key
    )

    session["conversation_history"] = [{"role": "assistant", "content": narrative}]

    return jsonify({
        "narrative":      narrative,
        "state":          _public_state(state, summary),
        "status":         "continue",
        "narrative_mode": narr_mode,
        "story":          {"id": story["id"], "title": story["title"], "color": story["color"], "icon": story["icon"]}
    })


@app.route("/api/action", methods=["POST"])
def player_action():
    """Process one player turn through the full quantum pipeline."""
    body = request.get_json(silent=True) or {}
    raw_input = (body.get("action") or "").strip()
    api_key   = body.get("api_key", "") or os.environ.get("TAMUS_AI_CHAT_API_KEY", "")

    if not raw_input:
        return jsonify({"error": "No action provided."}), 400

    # Retrieve session state
    state    = session.get("game_state")
    history  = session.get("conversation_history", [])
    story_id = session.get("story_id", "qlab7")
    story    = STORIES_BY_ID.get(story_id, STORIES_BY_ID["qlab7"])

    if not state:
        return jsonify({"error": "No active game. Please start a new game."}), 400

    # ── Pipeline ──────────────────────────────────────────────────────────────

    # Step 1: auto-update (prism_shard effects, etc.)
    state = auto_update_state(state)

    # Step 2: parse intent
    intent = parse_intent(raw_input)

    # Step 2b: room-object presence check (quantum_rules leaves this to the engine)
    # If the player tries to take/examine an object not in the current room,
    # short-circuit with an in-world blocked message before calling is_valid_action.
    if intent.verb in ("take", "examine") and intent.object_id:
        current_room_objects = GAME_DATA["rooms"].get(state["current_room"], {}).get("objects", [])
        obj_in_room = intent.object_id in current_room_objects
        obj_in_inv  = intent.object_id in state.get("inventory", [])
        # Allow if: object is in this room OR it's already in inventory (examine held items)
        if not obj_in_room and not obj_in_inv and intent.object_id not in ("", "unknown"):
            blocked_validation = ValidationResult(
                is_valid=False,
                reason="Whatever you are reaching for isn't here. The room offers nothing of that kind."
            )
            blocked_result = type("GameResult", (), {"status": "continue", "message": ""})()
            summary = get_quantum_state_summary(state)
            narrative, narr_mode = generate_narrative(
                game_state=state, game_data=GAME_DATA,
                intent=intent, validation=blocked_validation,
                quantum_event=None, game_result=blocked_result,
                summary=summary, conversation_history=history,
                story=story, api_key=api_key
            )
            history.append({"role": "user",      "content": raw_input})
            history.append({"role": "assistant",  "content": narrative})
            session["game_state"] = state
            session["conversation_history"] = history
            return jsonify({
                "narrative":      narrative,
                "state":          _public_state(state, summary),
                "status":         "continue",
                "message":        "",
                "narrative_mode": narr_mode
            })

    # Step 3: validate
    validation = is_valid_action(intent, state)

    quantum_event = None

    if not validation.is_valid:
        # Blocked action — quantum_event may carry a game_over (Observer catch)
        quantum_event = validation.quantum_event
        if quantum_event and quantum_event.event_type == "game_over":
            game_result = type("GameResult", (), {"status": "lose", "message": quantum_event.narrative_hint})()
        else:
            game_result = type("GameResult", (), {"status": "continue", "message": ""})()
    else:
        # Step 4: apply quantum effects
        state, quantum_event = apply_quantum_effect(intent, state)

        # Step 5: entanglement cascade
        state, cascade_events = check_entanglement_cascade(intent.object_id, intent.verb, state)
        if cascade_events and not quantum_event:
            quantum_event = cascade_events[0]
        elif cascade_events and quantum_event and quantum_event.event_type == "no_op":
            quantum_event = cascade_events[0]

        # Step 6: movement
        state = _apply_movement(intent, state)

        # Step 7: increment turn
        state["turn"] = state.get("turn", 0) + 1

        # Step 8: win/lose evaluation
        game_result = evaluate_win_loss(state, intent)

        # Handle ghost_bridge void → immediate lose
        if (quantum_event and quantum_event.event_type == "game_over"):
            game_result = type("GameResult", (), {
                "status": "lose",
                "message": quantum_event.narrative_hint
            })()

    # Step 9: state summary
    summary = get_quantum_state_summary(state)

    # Step 10: generate narrative
    narrative, narr_mode = generate_narrative(
        game_state=state,
        game_data=GAME_DATA,
        intent=intent,
        validation=validation,
        quantum_event=quantum_event,
        game_result=game_result,
        summary=summary,
        conversation_history=history,
        story=story,
        api_key=api_key
    )

    # Update conversation history (user action + assistant narrative)
    history.append({"role": "user",      "content": raw_input})
    history.append({"role": "assistant", "content": narrative})

    # Persist
    session["game_state"] = state
    session["conversation_history"] = history

    return jsonify({
        "narrative":      narrative,
        "state":          _public_state(state, summary),
        "status":         game_result.status,
        "message":        game_result.message or "",
        "narrative_mode": narr_mode
    })


@app.route("/api/reset", methods=["POST"])
def reset_game():
    """Clear session data (soft reset — client calls /api/start for a new game)."""
    session.clear()
    return jsonify({"ok": True})


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _public_state(state: dict, summary: dict) -> dict:
    """Build the JSON payload the frontend consumes for the status bar."""
    room_id   = state["current_room"]
    room      = GAME_DATA["rooms"][room_id]
    obj_states = state.get("object_states", {})

    visible = [
        GAME_DATA["objects"][oid]["display_name"]
        for oid in room["objects"]
        if obj_states.get(oid) not in ("held", None)
    ]

    return {
        "room_id":          room_id,
        "room_name":        room["name"],
        "turn":             state.get("turn", 0),
        "turns_remaining":  summary["turns_remaining"],
        "inventory":        summary["inventory_display"],
        "observer_status":  summary["observer_status"],
        "visible_objects":  visible,
        "exits":            list(room["exits"].keys()),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--no-debug", action="store_true", help="Disable debug mode")
    args = parser.parse_args()
    app.run(debug=not args.no_debug, host=args.host, port=args.port)
