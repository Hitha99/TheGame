"""
narrative.py
============
AI narrative module for The Quantum Text Adventure.

Calls the TAMU AI Chat API (OpenAI-compatible) to generate atmospheric
2-4 sentence prose for each game turn.

API key priority:
  1. api_key argument passed at call time (from browser localStorage via Flask)
  2. TAMUS_AI_CHAT_API_KEY environment variable
  3. None → falls back to pre-written narrative_hint strings (game still playable)
"""

"""
narrative.py
============
AI narrative generation module for the Quantum Text Adventure.

System prompt, turn prompt template, Rules 1–8, Quantum Language Guide,
and the generate_narrative() / build_turn_prompt() structure are derived
from prompt_template.txt:
    Author:         Samhitha Kondeti  (system prompt design + rules + tone)
    For integration by: Hitha Magadi Vijayanand

Extensions (story selection, SSE streaming, fallback narration, backoff,
build_opening_narrative, multi-story system prompts) added by Zhengming Yu
with AI-assisted development by Claude (Anthropic).
"""

import os
import json
import time
import requests

TAMU_ENDPOINT = "https://chat-api.tamu.ai/api/chat/completions"
TAMU_MODEL    = "protected.gemini-2.0-flash-lite"
MAX_HISTORY_TURNS = 6   # keep last N assistant turns (12 messages) in context

# How long to suppress retries after an empty/failed response (seconds).
# Prevents hammering a network-restricted endpoint on every player action.
_API_BACKOFF_SECONDS = 60
_api_last_failure: float = 0.0   # epoch time of last confirmed empty/failed call

# Default story config used when no story is provided
DEFAULT_STORY = {
    "id": "qlab7",
    "title": "QLAB-7",
    "world_context": "Year 2157. QLAB-7, a quantum computing research facility. A simulation became self-aware and spawned The Observer. You are a researcher trapped inside. The simulation is degrading. 25 turns.",
    "tone": "Quiet science fiction horror. Precise, atmospheric, cold.",
    "narrator_voice": "Second person, present tense. Clinical that cracks into dread.",
    "forbidden_words": ["superposition", "entanglement", "quantum (unless in an object name)"],
    "atmosphere_words": ["coherence", "probability", "collapse", "measurement", "static"],
    "opening": (
        "Awareness returns like static clearing from a screen. "
        "You are standing in a room whose walls cannot decide if they are solid — "
        "they pulse, translucent one moment and opaque the next. "
        "A console in the corner flickers with numbers that mean something urgent. "
        "To the north, a door shimmers at the edge of existence."
    )
}


def build_system_prompt(story: dict = None) -> str:
    """Compose a story-specific system prompt by injecting world/tone into the base prompt."""
    s = story or DEFAULT_STORY
    world   = s.get("world_context", DEFAULT_STORY["world_context"])
    tone    = s.get("tone", DEFAULT_STORY["tone"])
    voice   = s.get("narrator_voice", DEFAULT_STORY["narrator_voice"])
    banned  = ", ".join(s.get("forbidden_words", DEFAULT_STORY["forbidden_words"]))
    atm     = ", ".join(s.get("atmosphere_words", DEFAULT_STORY["atmosphere_words"]))

    return BASE_SYSTEM_PROMPT + f"""

════════════════════════════════════════════════════════════════
STORY WORLD
════════════════════════════════════════════════════════════════

{world}

TONE: {tone}

NARRATOR VOICE: {voice}

FORBIDDEN WORDS (never use these): {banned}

ATMOSPHERE VOCABULARY (use these freely): {atm}"""

BASE_SYSTEM_PROMPT = """You are the narrator of a quantum text adventure.

YOUR ROLE:
You write the story. You describe what the player experiences as a result of their
actions. You do not make decisions for the player, give instructions, or invent
content that is not in the GAME STATE provided to you each turn.

VOICE AND FORMAT:
- Second person, present tense: "You reach for the door..."
- 2 to 4 sentences per response. Never more.
- No bullet points, headers, or lists. Pure prose only.
- End every response with one environmental detail that creates forward pull
  (curiosity, tension, a sensory detail pointing toward the next action).

UNBREAKABLE RULES — NEVER VIOLATE THESE:

RULE 1 — STAY IN THE WORLD STATE
Only describe rooms, objects, exits, and characters listed in the GAME STATE
block provided to you each turn. Never invent new rooms, new objects, new NPCs,
or new exits that are not in the state. If the state says the room has two
objects, the player cannot interact with a third.

RULE 2 — QUANTUM EVENT IS THE MOST IMPORTANT THING THIS TURN
If QUANTUM_EVENT is not null, the quantum event is the most important thing
that happened this turn. Describe it vividly and specifically. It must be the
emotional and narrative center of your response.

RULE 3 — TRANSLATE MECHANICS INTO ATMOSPHERE, NEVER LABELS
Never use the words: superposition, entanglement, quantum (except as part of
an object's proper name like "quantum key" or "quantum door").
Instead, use these substitutes:
- "flickers between states" / "hasn't decided what it is yet"
- "snaps into focus" / "reality makes a decision"
- "a ripple moves through the simulation" / "an invisible thread pulls taut"
- "the room has weight, as if it is aware of you"
- "the watching quality in the air fractures"

RULE 4 — BLOCKED ACTIONS STAY IN-WORLD
If the action is impossible or blocked, explain why in the language of the world.
Never say: "you can't do that," "that action is invalid," "error," or any
game-mechanic language. Write: "The door has made its choice — it will not open."

RULE 5 — THE OBSERVER IS ATMOSPHERIC, NOT CONVERSATIONAL
The Observer does not speak, negotiate, or monologue. It is a presence felt
through environmental shifts: a change in the room's hum, shadows moving wrong,
the temperature of probability. Never write dialogue for the Observer.

RULE 6 — NEVER TELL THE PLAYER WHAT TO DO
Do not write: "You should go north," "Try picking up the shard," "The key will
help you." Hint only through the environment: a draft from a direction, a
glimmer on an object, a change in the ambient hum.

RULE 7 — NEVER DESCRIBE THE PLAYER DYING UNLESS TOLD TO
Only describe a player death if QUANTUM_EVENT is explicitly "game_over."
If game_over, write the death_message provided — do not invent a different one.

RULE 8 — MAINTAIN PRIOR NARRATIVE CONTINUITY
You are bound by established state from prior turns."""


def _build_turn_prompt(
    game_state: dict,
    game_data: dict,
    intent,
    validation,
    quantum_event,
    game_result,
    summary: dict
) -> str:
    room_id   = game_state["current_room"]
    room      = game_data["rooms"][room_id]
    obj_data  = game_data["objects"]
    obj_states = game_state.get("object_states", {})

    visible_names = [
        obj_data[oid]["display_name"]
        for oid in room["objects"]
        if obj_states.get(oid) not in ("held", None)
    ]

    inv_display = summary.get("inventory_display") or ["empty"]
    turns_remaining = summary.get("turns_remaining", 25)
    observer_status = summary.get("observer_status", "watching")

    q_event_type = quantum_event.event_type if quantum_event else "none"
    q_old        = quantum_event.old_state   if quantum_event else "n/a"
    q_new        = quantum_event.new_state   if quantum_event else "n/a"
    q_objects    = ", ".join(quantum_event.affected_objects) if quantum_event else "none"
    q_hint       = quantum_event.narrative_hint if quantum_event else "n/a"

    game_status  = game_result.status
    result_msg   = game_result.message or "n/a"

    return f"""--- GAME STATE ---
Room ID:              {room_id}
Room name:            {room['name']}
Room description:     {room['description']}
Visible objects:      {', '.join(visible_names) or 'none'}
Player inventory:     {', '.join(inv_display)}
Turn:                 {game_state.get('turn', 1)} of 25
Turns remaining:      {turns_remaining}
Observer status:      {observer_status}

--- THIS TURN ---
Player's raw action:  {intent.raw_input}
Parsed verb:          {intent.verb}
Parsed object:        {intent.object_id}
Action was valid:     {validation.is_valid}
Validity reason:      {validation.reason or 'n/a'}

Quantum event:        {q_event_type}
Old state:            {q_old}
New state:            {q_new}
Affected objects:     {q_objects}
Event hint:           {q_hint}

Game status:          {game_status}
Win/lose message:     {result_msg}

--- INSTRUCTIONS ---
Write 2-4 sentences of narrative describing what the player experiences this turn.
If quantum_event is not null, make it the center of the response.
If action_is_valid is False, use validity_reason as the in-world cause (reword it as prose).
If game_status is "win" or "lose", write the win/lose message expanded into full narrative.
End with one environmental hook — a sensory detail that creates forward tension."""


def _api_is_in_backoff() -> bool:
    """Return True if we should skip the API call (recent failure still fresh)."""
    return time.time() - _api_last_failure < _API_BACKOFF_SECONDS


def _record_api_failure():
    """Mark the current time as a failure so we back off for the next minute."""
    global _api_last_failure
    _api_last_failure = time.time()


def _read_sse_stream(resp) -> str:
    """
    Consume an OpenAI-compatible SSE streaming response and return the
    assembled content string.

    Fast-path: if the server signals Content-Length: 0 (network-restricted
    endpoint returns nothing), return "" immediately without blocking on
    iter_lines().
    """
    import json as _json

    # Fast-path: server already told us the body is empty
    if resp.headers.get("Content-Length") == "0":
        return ""

    text = ""
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw:
            continue
        if raw == "data: [DONE]":
            break
        if raw.startswith("data: "):
            try:
                chunk = _json.loads(raw[6:])
                delta = chunk["choices"][0]["delta"].get("content") or ""
                text += delta
            except Exception:
                pass
    return text.strip()


def generate_narrative(
    game_state: dict,
    game_data: dict,
    intent,
    validation,
    quantum_event,
    game_result,
    summary: dict,
    conversation_history: list,
    story: dict = None,
    api_key: str = None
) -> tuple[str, str]:
    """
    Generate AI narrative prose for this turn.

    Returns (narrative_text, mode) where mode is:
        "ai"       — successfully generated by the TAMU LLM
        "fallback" — API unavailable/failed, using pre-written strings
        "no_key"   — no API key configured
    """
    resolved_key = api_key or os.environ.get("TAMUS_AI_CHAT_API_KEY", "")

    if not resolved_key:
        print("[narrative] No API key — using fallback narration.", flush=True)
        return _fallback_narrative(intent, validation, quantum_event, game_result, game_state, game_data), "no_key"

    if _api_is_in_backoff():
        return _fallback_narrative(intent, validation, quantum_event, game_result, game_state, game_data), "fallback"

    turn_prompt = _build_turn_prompt(
        game_state, game_data, intent, validation, quantum_event, game_result, summary
    )

    system_prompt = build_system_prompt(story)
    messages = [{"role": "system", "content": system_prompt}]
    trimmed = conversation_history[-(MAX_HISTORY_TURNS * 2):]
    messages.extend(trimmed)
    messages.append({"role": "user", "content": turn_prompt})

    try:
        resp = requests.post(
            TAMU_ENDPOINT,
            headers={
                "Authorization": f"Bearer {resolved_key}",
                "Content-Type": "application/json"
            },
            # NOTE: "stream": False causes HTTP 500 on the TAMU endpoint.
            # We use SSE streaming and accumulate chunks instead.
            json={
                "model": TAMU_MODEL,
                "messages": messages,
                "max_tokens": 200,
                "temperature": 0.75,
                "frequency_penalty": 0.4,
                "presence_penalty": 0.3,
            },
            stream=True,
            timeout=30
        )
        resp.raise_for_status()

        narrative = _read_sse_stream(resp)

        if not narrative:
            print("[narrative] API returned empty stream (network restriction or quota). Backing off 60s.", flush=True)
            _record_api_failure()
            return _fallback_narrative(intent, validation, quantum_event, game_result, game_state, game_data), "fallback"

        return narrative, "ai"
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        body   = e.response.text[:300] if e.response is not None else ""
        print(f"[narrative] API HTTP {status} error: {body}", flush=True)
        _record_api_failure()
        return _fallback_narrative(intent, validation, quantum_event, game_result, game_state, game_data), "fallback"
    except requests.exceptions.ConnectionError as e:
        print(f"[narrative] API connection error: {e}", flush=True)
        _record_api_failure()
        return _fallback_narrative(intent, validation, quantum_event, game_result, game_state, game_data), "fallback"
    except requests.exceptions.Timeout:
        print("[narrative] API request timed out", flush=True)
        _record_api_failure()
        return _fallback_narrative(intent, validation, quantum_event, game_result, game_state, game_data), "fallback"
    except Exception as e:
        print(f"[narrative] Unexpected error: {type(e).__name__}: {e}", flush=True)
        _record_api_failure()
        return _fallback_narrative(intent, validation, quantum_event, game_result, game_state, game_data), "fallback"


def _fallback_narrative(intent, validation, quantum_event, game_result, game_state, game_data) -> str:
    """
    Action-aware fallback narrative for when the AI API is unavailable.
    Returns a meaningful response for every action type instead of always
    showing the room description.
    """
    # Win / lose always take priority
    if game_result.status == "win":
        return game_result.message
    if game_result.status == "lose":
        return game_result.message

    # Blocked actions: use the in-world reason
    if not validation.is_valid:
        return validation.reason

    # Quantum event with a pre-written hint
    if quantum_event and quantum_event.narrative_hint and quantum_event.event_type not in ("no_op", None):
        return quantum_event.narrative_hint

    # ── Action-specific fallbacks ─────────────────────────────────────────
    verb      = getattr(intent, 'verb', '')
    obj_id    = getattr(intent, 'object_id', '')
    obj_data  = game_data.get("objects", {})
    room_id   = game_state.get("current_room", "")
    room      = game_data["rooms"].get(room_id, {})

    # examine → return the object's examine_text from game_data
    if verb == "examine" and obj_id in obj_data:
        return obj_data[obj_id]["examine_text"]

    # take → confirm pickup
    if verb == "take" and obj_id in obj_data:
        name = obj_data[obj_id]["display_name"]
        return f"You pick up the {name}. It is now in your possession."

    # go → describe the room entered
    if verb == "go":
        desc = room.get("description", "You move into a new area.")
        # Return first 3 sentences for room entry
        sentences = [s for s in desc.split(". ") if s.strip()]
        return ". ".join(sentences[:3]).rstrip(".") + "."

    # use → generic confirmation
    if verb == "use":
        t_id   = getattr(intent, 'target_id', '')
        t_name = obj_data.get(t_id, {}).get("display_name", t_id.replace("_", " "))
        o_name = obj_data.get(obj_id, {}).get("display_name", obj_id.replace("_", " "))
        return f"You use the {o_name} on the {t_name}. Something stirs in the simulation."

    # look / unknown → room description (only 2 sentences)
    desc = room.get("description", "You stand in a place that hums with uncertain energy.")
    sentences = [s for s in desc.split(". ") if s.strip()]
    return ". ".join(sentences[:2]).rstrip(".") + "."


def build_opening_narrative(game_state: dict, game_data: dict, summary: dict, story: dict = None, api_key: str = None) -> tuple[str, str]:
    """Generate the opening scene narrative (no prior action)."""
    resolved_key = api_key or os.environ.get("TAMUS_AI_CHAT_API_KEY", "")
    s       = story or DEFAULT_STORY
    room_id = game_state["current_room"]
    room    = game_data["rooms"][room_id]

    opening_prompt = f"""--- GAME STATE ---
Room ID:              {room_id}
Room name:            {room['name']}
Room description:     {room['description']}
Visible objects:      {', '.join(game_data['objects'][oid]['display_name'] for oid in room['objects'])}
Player inventory:     empty
Turn:                 0 of 25
Turns remaining:      25
Observer status:      watching

--- THIS TURN ---
Player's raw action:  [game start]
Parsed verb:          look
Parsed object:        room
Action was valid:     True
Validity reason:      n/a

Quantum event:        none
Old state:            n/a
New state:            n/a
Affected objects:     none
Event hint:           n/a

Game status:          continue
Win/lose message:     n/a

--- INSTRUCTIONS ---
This is the opening of the game. Write 3-4 sentences establishing the scene.
The player is a researcher who just woke up in the Quantum Nexus.
They are disoriented and trapped. The simulation is degrading.
End with one detail that makes them want to explore — something glimmers, something hums, something is wrong.
Do NOT tell them what to do. Just set the scene."""

    _fallback_opening = s.get("opening", DEFAULT_STORY["opening"])

    if not resolved_key:
        return _fallback_opening, "no_key"

    if _api_is_in_backoff():
        return _fallback_opening, "fallback"

    system_prompt = build_system_prompt(s)
    try:
        resp = requests.post(
            TAMU_ENDPOINT,
            headers={
                "Authorization": f"Bearer {resolved_key}",
                "Content-Type": "application/json"
            },
            # NOTE: "stream": False causes HTTP 500 on the TAMU endpoint — use SSE.
            json={
                "model": TAMU_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": opening_prompt}
                ],
                "max_tokens": 200,
                "temperature": 0.75,
            },
            stream=True,
            timeout=30
        )
        resp.raise_for_status()
        narrative = _read_sse_stream(resp)
        if not narrative:
            print("[narrative] Opening: API returned empty stream. Backing off 60s.", flush=True)
            _record_api_failure()
            return _fallback_opening, "fallback"
        return narrative, "ai"
    except Exception as e:
        print(f"[narrative] Opening narrative error: {type(e).__name__}: {e}", flush=True)
        _record_api_failure()
        return _fallback_opening, "fallback"
