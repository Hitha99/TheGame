"""
quantum_rules.py
================
Quantum mechanics module for "The Game."

Author:      Samhitha Kondeti  (rules design + content)
Integrate:   Bari Vadaria       (wire into state engine)
Calls from:  Zhengming Yu / Carrigan Royer (state engine → Flask route)

This module is intentionally self-contained and side-effect free.
Every function takes a game_state dict and returns a NEW game_state dict.
The original state is never mutated — always copy.deepcopy() first.

Call order per player turn (from state engine):
    1. parse_intent(raw_text)              → ActionIntent
    2. is_valid_action(intent, state)      → ValidationResult
    3. apply_quantum_effect(intent, state) → (new_state, QuantumEvent | None)
    4. check_entanglement_cascade(...)     → (new_state, list[QuantumEvent])
    5. evaluate_win_loss(state, intent)    → GameResult
    6. get_quantum_state_summary(state)    → dict   (sent to frontend + AI prompt)

Usage example (in your Flask route):
    intent = parse_intent(request.json["action"])
    validation = is_valid_action(intent, game_state)
    if not validation.is_valid:
        return {"error": validation.reason}
    new_state, event = apply_quantum_effect(intent, game_state)
    new_state, cascade_events = check_entanglement_cascade(intent.object_id, intent.verb, new_state)
    result = evaluate_win_loss(new_state, intent)
    summary = get_quantum_state_summary(new_state)
    # → pass new_state + event + result + summary to AI narrative module
"""

import random
import copy
from dataclasses import dataclass, field
from typing import Optional


# ═══════════════════════════════════════════════════════════
# SECTION 1 — RULE CONSTANTS
# ═══════════════════════════════════════════════════════════
# These are the single source of truth for all quantum rules.
# Change mechanics here — nowhere else.

SUPERPOSITION_OBJECTS: dict = {
    "quantum_door": {
        "collapse_trigger": "examine",
        "collapse_type": "random",
        "possible_states": ["open", "closed"],
        "collapse_weights": [0.6, 0.4],
        "narrative_hints": {
            "open":   "The door snaps open. It was always going to be open. Probably.",
            "closed": "The door slams shut with a finality that feels retroactive. It was always going to be closed.",
        }
    },
    "ghost_bridge": {
        "collapse_trigger": "examine",
        "collapse_type": "player_declared",
        "possible_states": ["solid", "void"],
        "collapse_weights": None,    # player declaration determines outcome
        "narrative_hints": {
            "solid": "The bridge solidifies the moment certainty enters your mind. It always was.",
            "void":  "The bridge dissolves. There was never a bridge.",
        }
    }
}

ENTANGLED_PAIRS: dict = {
    "mirror_key": {
        "partner": "locked_mirror",
        "trigger_action": "take",
        "effect_on_partner": {"state_change": "unlocked"},
        "narrative_hint": (
            "As you pick up the mirror key, a ripple moves through the simulation — "
            "something in a room you haven't visited yet just changed its mind."
        )
    }
}

OBSERVER_GATED_OBJECTS: dict = {
    "quantum_key": {
        "required_inventory": ["prism_shard"],
        "fail_quantum_event": "game_over",
        "fail_message": (
            "The Observer's gaze collapses every quantum state in the room against you "
            "simultaneously. You never had a chance."
        ),
        "success_cascade": {
            "target_object": "observer_entity",
            "target_state": "defeated"
        }
    }
}

EXIT_REQUIREMENTS: dict = {
    "quantum_nexus": {
        "north": {
            "object_state": {"quantum_door": "open"},
            "fail_message": (
                "The door has solidified into a closed state. "
                "This path is sealed by its own observation."
            )
        }
    },
    "superposition_vault": {
        "across": {
            "object_state": {
                "ghost_bridge": "solid",
                "locked_mirror": "unlocked"
            },
            "fail_message": (
                "The way across is not ready. Something on this side of the chasm "
                "still hasn't resolved."
            )
        }
    },
    "observer_chamber": {
        "north": {
            "inventory_contains": ["quantum_key"],
            "fail_message": (
                "The passage to the core is sealed. "
                "Something about this exit requires the right key."
            )
        }
    }
}

WIN_CONDITION: dict = {
    "room": "core",
    "verb": "use",
    "object_id": "quantum_key",
    "target_id": "core_stabilizer",
    "inventory_requires": ["quantum_key"]
}

LOSE_CONDITIONS: list = [
    {
        "id": "turn_limit",
        "check": lambda state: state.get("turn", 0) > 25,
        "message": (
            "The simulation's coherence reaches zero. Reality dissolves around you. "
            "The quantum foam consumes everything."
        )
    },
    {
        "id": "ghost_bridge_void",
        "check": lambda state: state.get("object_states", {}).get("ghost_bridge") == "void",
        "message": "You hesitated. The bridge became nothing. The chasm is absolute."
    }
]

# Keywords the parser uses to detect player declaration on ghost_bridge
SOLID_KEYWORDS = ["solid", "real", "there", "yes", "believe", "trust", "step", "cross"]
VOID_KEYWORDS  = ["void", "not", "nothing", "empty", "doubt", "unsure", "fake", "no"]


# ═══════════════════════════════════════════════════════════
# SECTION 2 — DATA TYPES
# ═══════════════════════════════════════════════════════════

@dataclass
class ActionIntent:
    """Parsed representation of a player's raw text input."""
    verb: str            # "examine" | "take" | "use" | "go" | "look" | "drop"
    object_id: str       # canonical object or direction id, e.g. "quantum_door", "north"
    target_id: str = ""  # for "use X on Y" — Y goes here
    declaration: str = ""  # raw player text, used for superposition_declared collapse
    raw_input: str = ""    # original unmodified player input


@dataclass
class QuantumEvent:
    """Describes a quantum event that occurred during action resolution.
    
    Passed to the AI narrative module so it can write accurate narration.
    Also logged to game_state["quantum_events_log"].
    """
    event_type: str           # see EVENT_TYPES below
    object_id: str
    old_state: str
    new_state: str
    affected_objects: list = field(default_factory=list)
    narrative_hint: str = ""  # pre-written hint for AI prompt (can override)

    # Valid event_type values:
    # "superposition_resolved"    — random or declared collapse
    # "entanglement_triggered"    — picking up an entangled object changed its partner
    # "observer_defeated"         — player took quantum_key with prism_shard
    # "game_over"                 — lose condition triggered
    # "win"                       — win condition triggered
    # "no_op"                     — nothing quantum happened this turn


@dataclass
class ValidationResult:
    """Result of is_valid_action(). 
    
    If is_valid is False, return reason to the frontend directly —
    do NOT pass the action to the state engine. Reason is in-world language.
    """
    is_valid: bool
    reason: str = ""  # in-world phrasing, not "you can't do that"
    quantum_event: Optional[QuantumEvent] = None


@dataclass
class GameResult:
    """Status after evaluate_win_loss().
    
    status values: "win" | "lose" | "continue"
    """
    status: str
    message: str = ""


# ═══════════════════════════════════════════════════════════
# SECTION 3 — INTENT PARSER
# ═══════════════════════════════════════════════════════════

# Verb synonym map — extend this as needed
_VERB_MAP: dict[str, str] = {
    # examine synonyms
    "look": "examine", "look at": "examine", "inspect": "examine",
    "check": "examine", "study": "examine", "observe": "examine",
    "read": "examine", "view": "examine", "see": "examine",
    # take synonyms
    "take": "take", "pick up": "take", "pick": "take", "grab": "take",
    "get": "take", "collect": "take", "lift": "take",
    # go synonyms
    "go": "go", "walk": "go", "move": "go", "head": "go",
    "travel": "go", "enter": "go", "leave": "go", "exit": "go",
    "step": "go", "cross": "go",
    # use synonyms
    "use": "use", "activate": "use", "apply": "use",
    "insert": "use", "place": "use", "put": "use",
}

# Object alias map — player may say any alias, maps to canonical id
_OBJECT_ALIASES: dict[str, str] = {
    "console": "flickering_console", "flickering console": "flickering_console",
    "terminal": "flickering_console", "screen": "flickering_console",
    "door": "quantum_door", "quantum door": "quantum_door", "north door": "quantum_door",
    "shard": "prism_shard", "crystal": "prism_shard",
    "prism": "prism_shard", "prism shard": "prism_shard",
    "key": "mirror_key", "mirror key": "mirror_key",
    "node": "entanglement_node", "entanglement node": "entanglement_node",
    "mirror": "locked_mirror", "locked mirror": "locked_mirror",
    "bridge": "ghost_bridge", "ghost bridge": "ghost_bridge",
    "quantum key": "quantum_key",
    "observer": "observer_entity", "the observer": "observer_entity",
    "core": "core_stabilizer", "core stabilizer": "core_stabilizer", "pillar": "core_stabilizer",
    # directions
    "north": "north", "south": "south", "east": "east",
    "west": "west", "across": "across", "over": "across",
}


def parse_intent(raw_text: str) -> ActionIntent:
    """
    Convert free-form player text into a structured ActionIntent.
    
    This is a lightweight keyword parser — not NLP. It covers the verbs and
    objects defined in this game. Pass unknown inputs through as-is; the
    state engine will handle graceful failure.

    Args:
        raw_text: The player's raw input string, e.g. "examine the quantum door"

    Returns:
        ActionIntent with verb, object_id, target_id, declaration, raw_input

    Examples:
        parse_intent("look at the quantum door")
        → ActionIntent(verb="examine", object_id="quantum_door", ...)

        parse_intent("use quantum key on core stabilizer")
        → ActionIntent(verb="use", object_id="quantum_key", target_id="core_stabilizer", ...)

        parse_intent("I believe the bridge is solid")
        → ActionIntent(verb="examine", object_id="ghost_bridge", declaration="solid", ...)
    """
    text = raw_text.lower().strip()
    intent = ActionIntent(verb="unknown", object_id="", raw_input=raw_text, declaration=raw_text)

    # — Detect verb —
    found_verb = None
    for alias, canonical in sorted(_VERB_MAP.items(), key=lambda x: -len(x[0])):
        if alias in text:
            found_verb = canonical
            break
    intent.verb = found_verb or "examine"  # default to examine if ambiguous

    # — Detect "use X on Y" pattern —
    if intent.verb == "use" and " on " in text:
        parts = text.split(" on ", 1)
        left = parts[0]
        right = parts[1]
        for alias, obj_id in _OBJECT_ALIASES.items():
            if alias in left:
                intent.object_id = obj_id
            if alias in right:
                intent.target_id = obj_id

    # — Detect primary object —
    if not intent.object_id:
        for alias, obj_id in sorted(_OBJECT_ALIASES.items(), key=lambda x: -len(x[0])):
            if alias in text:
                intent.object_id = obj_id
                break

    # — Detect player declaration for ghost_bridge —
    if "bridge" in text or intent.object_id == "ghost_bridge":
        intent.object_id = "ghost_bridge"
        if any(w in text for w in SOLID_KEYWORDS):
            intent.declaration = "solid"
        elif any(w in text for w in VOID_KEYWORDS):
            intent.declaration = "void"

    return intent


# ═══════════════════════════════════════════════════════════
# SECTION 4 — VALIDATION
# ═══════════════════════════════════════════════════════════

def is_valid_action(intent: ActionIntent, game_state: dict) -> ValidationResult:
    """
    Check whether a parsed action is legal given the current game state.
    Must be called BEFORE apply_quantum_effect().
    
    Returns ValidationResult(is_valid=False, reason=<in-world string>)
    if the action is blocked. The reason string is safe to display to the player.

    Args:
        intent:     Parsed ActionIntent from parse_intent()
        game_state: Current game state dict (from state engine)

    Returns:
        ValidationResult

    Examples:
        is_valid_action(ActionIntent("take", "quantum_key"), state_without_prism)
        → ValidationResult(False, "The Observer's gaze collapses every quantum state...")

        is_valid_action(ActionIntent("go", "north"), state_with_closed_door)
        → ValidationResult(False, "The door has solidified into a closed state...")
    """
    current_room: str = game_state.get("current_room", "")
    inventory: list  = game_state.get("inventory", [])
    obj_states: dict = game_state.get("object_states", {})

    # — Rule: observer-gated object take —
    if intent.verb == "take" and intent.object_id in OBSERVER_GATED_OBJECTS:
        gate = OBSERVER_GATED_OBJECTS[intent.object_id]
        if not all(item in inventory for item in gate["required_inventory"]):
            return ValidationResult(
                is_valid=False,
                reason=gate["fail_message"],
                quantum_event=QuantumEvent(
                    event_type="game_over",
                    object_id=intent.object_id,
                    old_state=obj_states.get(intent.object_id, "guarded"),
                    new_state="fail",
                    narrative_hint=gate["fail_message"]
                )
            )

    # — Rule: exit blocked by collapsed object —
    if intent.verb == "go":
        direction = intent.object_id
        room_reqs = EXIT_REQUIREMENTS.get(current_room, {})
        dir_reqs  = room_reqs.get(direction, {})

        if dir_reqs:
            for obj_id, required_state in dir_reqs.get("object_state", {}).items():
                actual_state = obj_states.get(obj_id, "")
                if actual_state != required_state:
                    return ValidationResult(
                        is_valid=False,
                        reason=dir_reqs["fail_message"]
                    )
            for item in dir_reqs.get("inventory_contains", []):
                if item not in inventory:
                    return ValidationResult(
                        is_valid=False,
                        reason=dir_reqs["fail_message"]
                    )

    # — Rule: ghost_bridge requires declaration before examining —
    if intent.verb == "examine" and intent.object_id == "ghost_bridge":
        if obj_states.get("ghost_bridge") == "superposed" and not intent.declaration:
            return ValidationResult(
                is_valid=False,
                reason=(
                    "The bridge exists in superposition. "
                    "To observe it, you must declare what you believe it to be. "
                    "Do you believe it is solid?"
                )
            )

    # — Rule: can't take something not in this room —
    # (Carrigan: cross-check with room's objects list from game_data.json)

    # — Rule: use requires item in inventory —
    if intent.verb == "use":
        if intent.object_id not in inventory:
            return ValidationResult(
                is_valid=False,
                reason=f"You are not carrying the {intent.object_id.replace('_', ' ')}."
            )

    return ValidationResult(is_valid=True)


# ═══════════════════════════════════════════════════════════
# SECTION 5 — QUANTUM EFFECT APPLICATION
# ═══════════════════════════════════════════════════════════

def apply_superposition_collapse(
    obj_id: str,
    game_state: dict,
    player_declaration: str = ""
) -> tuple[dict, QuantumEvent]:
    """
    Collapse a superposed object into a definite state.

    For random collapse  (quantum_door): uses weighted random choice.
    For declared collapse (ghost_bridge): uses player_declaration ("solid" | "void").

    Args:
        obj_id:             ID of the superposed object
        game_state:         Current game state dict
        player_declaration: "solid" or "void" for player-declared collapses

    Returns:
        (new_game_state, QuantumEvent)

    Raises:
        ValueError if obj_id is not in SUPERPOSITION_OBJECTS

    Examples:
        new_state, event = apply_superposition_collapse("quantum_door", state)
        # → event.new_state is "open" or "closed" (randomly weighted)

        new_state, event = apply_superposition_collapse("ghost_bridge", state, "solid")
        # → event.new_state is "solid"
    """
    if obj_id not in SUPERPOSITION_OBJECTS:
        raise ValueError(f"'{obj_id}' is not a superposition object. Check SUPERPOSITION_OBJECTS.")

    new_state = copy.deepcopy(game_state)
    rule = SUPERPOSITION_OBJECTS[obj_id]
    old_state = new_state["object_states"].get(obj_id, "superposed")

    # Already collapsed — no-op
    if old_state != "superposed":
        return new_state, QuantumEvent(
            event_type="no_op",
            object_id=obj_id,
            old_state=old_state,
            new_state=old_state,
            narrative_hint=f"The {obj_id.replace('_', ' ')} has already resolved its state."
        )

    # Determine collapsed state
    if rule["collapse_type"] == "player_declared":
        resolved = "solid" if player_declaration == "solid" else "void"
    else:
        resolved = random.choices(
            rule["possible_states"],
            weights=rule["collapse_weights"],
            k=1
        )[0]

    new_state["object_states"][obj_id] = resolved

    event = QuantumEvent(
        event_type="superposition_resolved",
        object_id=obj_id,
        old_state="superposed",
        new_state=resolved,
        narrative_hint=rule["narrative_hints"].get(resolved, f"{obj_id} collapsed to {resolved}.")
    )

    # Ghost bridge void → game over flag
    if obj_id == "ghost_bridge" and resolved == "void":
        event.event_type = "game_over"
        event.narrative_hint = "You hesitated. The bridge became nothing. The chasm is absolute."

    new_state["quantum_events_log"].append({
        "turn": new_state.get("turn", 0),
        "event": event.event_type,
        "object": obj_id,
        "from": "superposed",
        "to": resolved
    })

    return new_state, event


def check_entanglement_cascade(
    trigger_obj_id: str,
    trigger_action: str,
    game_state: dict
) -> tuple[dict, list[QuantumEvent]]:
    """
    When a player action affects an entangled object, propagate the effect
    to its partner. Call this AFTER apply_quantum_effect().

    Args:
        trigger_obj_id:  The object the player acted on (e.g. "mirror_key")
        trigger_action:  The verb that triggered this (e.g. "take")
        game_state:      State dict AFTER the triggering action was applied

    Returns:
        (new_game_state, list_of_QuantumEvents)
        List is empty if no entanglement cascade occurred.

    Examples:
        new_state, events = check_entanglement_cascade("mirror_key", "take", state)
        # → events[0].affected_objects == ["locked_mirror"]
        # → new_state["object_states"]["locked_mirror"] == "unlocked"
    """
    new_state = copy.deepcopy(game_state)
    events: list[QuantumEvent] = []

    rule = ENTANGLED_PAIRS.get(trigger_obj_id)
    if not rule or rule["trigger_action"] != trigger_action:
        return new_state, events

    partner_id  = rule["partner"]
    effect      = rule["effect_on_partner"]
    old_partner = new_state["object_states"].get(partner_id, "unknown")

    if "state_change" in effect:
        new_state["object_states"][partner_id] = effect["state_change"]

    event = QuantumEvent(
        event_type="entanglement_triggered",
        object_id=trigger_obj_id,
        old_state=trigger_action,
        new_state=effect.get("state_change", "changed"),
        affected_objects=[partner_id],
        narrative_hint=rule["narrative_hint"]
    )
    events.append(event)

    new_state["quantum_events_log"].append({
        "turn": new_state.get("turn", 0),
        "event": "entanglement_triggered",
        "trigger": trigger_obj_id,
        "partner": partner_id,
        "partner_new_state": effect.get("state_change")
    })

    return new_state, events


def apply_quantum_effect(
    intent: ActionIntent,
    game_state: dict
) -> tuple[dict, Optional[QuantumEvent]]:
    """
    Top-level dispatcher: applies the correct quantum effect based on the
    action intent and current game state.

    Covers:
        - Superposition collapse (examine on a superposed object)
        - Observer-gated object success (take with correct inventory)
        - Basic state transitions (take pickable item, examine non-quantum object)

    Does NOT cover entanglement cascade — call check_entanglement_cascade()
    separately after this, passing the returned new_state.

    Args:
        intent:     Parsed ActionIntent
        game_state: Current game state dict

    Returns:
        (new_game_state, QuantumEvent or None)
    """
    new_state = copy.deepcopy(game_state)
    obj_states = new_state["object_states"]
    inventory  = new_state["inventory"]

    # — Superposition collapse on examine —
    if intent.verb == "examine" and intent.object_id in SUPERPOSITION_OBJECTS:
        current = obj_states.get(intent.object_id, "superposed")
        if current == "superposed":
            return apply_superposition_collapse(
                intent.object_id,
                new_state,
                player_declaration=intent.declaration
            )

    # — Observer-gated take (success path, failure handled in is_valid_action) —
    if intent.verb == "take" and intent.object_id in OBSERVER_GATED_OBJECTS:
        gate = OBSERVER_GATED_OBJECTS[intent.object_id]
        # State transitions: guarded → takeable → held
        obj_states[intent.object_id] = "held"
        if intent.object_id not in inventory:
            inventory.append(intent.object_id)

        # Apply cascade to observer entity
        cascade = gate.get("success_cascade", {})
        if cascade:
            obj_states[cascade["target_object"]] = cascade["target_state"]

        event = QuantumEvent(
            event_type="observer_defeated",
            object_id=intent.object_id,
            old_state="guarded",
            new_state="held",
            affected_objects=[cascade.get("target_object", "")],
            narrative_hint=(
                "You take the quantum key. The Observer fractures — "
                "its observing power collapses in on itself. Superposed. Powerless."
            )
        )
        return new_state, event

    # — Standard take (non-quantum object) —
    if intent.verb == "take":
        current = obj_states.get(intent.object_id, "")
        if current == "present":
            obj_states[intent.object_id] = "held"
            if intent.object_id not in inventory:
                inventory.append(intent.object_id)
        return new_state, None

    # — Standard examine (non-quantum) —
    if intent.verb == "examine":
        return new_state, None

    # — Use action —
    if intent.verb == "use":
        return new_state, None

    # — Movement —
    if intent.verb == "go":
        return new_state, None

    return new_state, None


# ═══════════════════════════════════════════════════════════
# SECTION 6 — WIN / LOSE EVALUATION
# ═══════════════════════════════════════════════════════════

def evaluate_win_loss(game_state: dict, intent: ActionIntent) -> GameResult:
    """
    Check win and lose conditions. Call this LAST, after all state updates.

    Args:
        game_state: The fully updated game state (after all quantum effects applied)
        intent:     The action that was just resolved

    Returns:
        GameResult with status "win", "lose", or "continue"

    Examples:
        evaluate_win_loss(state_at_core_with_key, use_intent)
        → GameResult(status="win", message="...")

        evaluate_win_loss(state_with_turn_26, any_intent)
        → GameResult(status="lose", message="...")
    """
    obj_states: dict = game_state.get("object_states", {})
    inventory: list  = game_state.get("inventory", [])
    current_room: str = game_state.get("current_room", "")

    # — Win condition —
    w = WIN_CONDITION
    if (current_room == w["room"]
            and intent.verb == w["verb"]
            and intent.object_id == w["object_id"]
            and intent.target_id == w["target_id"]
            and all(item in inventory for item in w["inventory_requires"])):
        return GameResult(
            status="win",
            message=(
                "The quantum key touches the core. Reality snaps into focus. "
                "For one crystalline moment, every superposition resolves, "
                "every entangled pair separates cleanly, and the Observer's gaze blinks out. "
                "The simulation ends. You go home."
            )
        )

    # — Lose conditions —
    for condition in LOSE_CONDITIONS:
        if condition["check"](game_state):
            return GameResult(status="lose", message=condition["message"])

    return GameResult(status="continue")


# ═══════════════════════════════════════════════════════════
# SECTION 7 — STATE SUMMARY (for frontend + AI prompt)
# ═══════════════════════════════════════════════════════════

def get_quantum_state_summary(game_state: dict) -> dict:
    """
    Produce a clean summary of quantum states for two consumers:
        1. Frontend status bar (observer_status, quantum_states)
        2. AI narrative prompt (superposed_objects, entanglement_status)

    Args:
        game_state: Current game state dict

    Returns:
        {
            "superposed_objects": [...],           # list of still-superposed obj ids
            "collapsed_objects":  {"id": "state"}, # already-observed objects
            "entanglement_status": [...],           # entangled pairs + whether triggered
            "observer_status": "watching"|"distracted"|"defeated",
            "turns_remaining": int,
            "inventory_display": [...]             # human-readable inventory names
        }

    Example return:
        {
            "superposed_objects": ["ghost_bridge"],
            "collapsed_objects": {"quantum_door": "open", "prism_shard": "held"},
            "entanglement_status": [
                {"object": "mirror_key", "partner": "locked_mirror", "triggered": True}
            ],
            "observer_status": "distracted",
            "turns_remaining": 18,
            "inventory_display": ["prism shard", "mirror key"]
        }
    """
    obj_states: dict = game_state.get("object_states", {})
    inventory: list  = game_state.get("inventory", [])
    turn: int        = game_state.get("turn", 0)

    superposed = [obj for obj, state in obj_states.items() if state == "superposed"]
    collapsed  = {obj: state for obj, state in obj_states.items() if state != "superposed"}

    entanglement_status = []
    for obj_id, rule in ENTANGLED_PAIRS.items():
        partner = rule["partner"]
        entanglement_status.append({
            "object":    obj_id,
            "partner":   partner,
            "triggered": obj_states.get(partner) not in ["locked", "unknown", None]
        })

    # Observer status logic
    observer_raw = obj_states.get("observer_entity", "watching")
    if observer_raw == "defeated":
        observer_status = "defeated"
    elif "prism_shard" in inventory:
        observer_status = "distracted"
    else:
        observer_status = "watching"

    # Human-readable inventory
    display_names = {
        "prism_shard": "prism shard",
        "mirror_key":  "mirror key",
        "quantum_key": "quantum key"
    }
    inventory_display = [display_names.get(item, item.replace("_", " ")) for item in inventory]

    return {
        "superposed_objects":   superposed,
        "collapsed_objects":    collapsed,
        "entanglement_status":  entanglement_status,
        "observer_status":      observer_status,
        "turns_remaining":      max(0, 25 - turn),
        "inventory_display":    inventory_display
    }


# ═══════════════════════════════════════════════════════════
# SECTION 8 — AUTO-STATE UPDATES (call once per turn start)
# ═══════════════════════════════════════════════════════════

def auto_update_state(game_state: dict) -> dict:
    """
    Apply state updates that should trigger automatically based on
    inventory or room changes — before processing the player's action.

    Currently handles:
        - quantum_key: guarded → takeable when prism_shard is in inventory
        - observer_entity: watching → distracted when prism_shard is in inventory

    Call at the START of each turn, before is_valid_action().

    Args:
        game_state: Current game state dict

    Returns:
        Updated game state dict (copy, not mutated in place)
    """
    new_state = copy.deepcopy(game_state)
    inventory  = new_state.get("inventory", [])
    obj_states = new_state["object_states"]

    # Prism shard in inventory → quantum_key becomes takeable, Observer distracted
    if "prism_shard" in inventory:
        if obj_states.get("quantum_key") == "guarded":
            obj_states["quantum_key"] = "takeable"
        if obj_states.get("observer_entity") == "watching":
            obj_states["observer_entity"] = "distracted"

    return new_state


# ═══════════════════════════════════════════════════════════
# SECTION 9 — QUICK TEST (run: python quantum_rules.py)
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import json

    # Minimal starting state for smoke-testing
    test_state = {
        "current_room": "quantum_nexus",
        "inventory": [],
        "turn": 1,
        "object_states": {
            "flickering_console": "unread",
            "quantum_door": "superposed",
            "prism_shard": "present",
            "mirror_key": "present",
            "entanglement_node": "inactive",
            "locked_mirror": "locked",
            "ghost_bridge": "superposed",
            "quantum_key": "guarded",
            "observer_entity": "watching",
            "core_stabilizer": "unstable"
        },
        "quantum_events_log": []
    }

    print("=" * 60)
    print("TEST 1: Parse 'examine the quantum door'")
    intent = parse_intent("examine the quantum door")
    print(f"  verb={intent.verb}, object={intent.object_id}")

    print("\nTEST 2: Validate + collapse quantum_door")
    val = is_valid_action(intent, test_state)
    print(f"  valid={val.is_valid}")
    if val.is_valid:
        new_state, event = apply_quantum_effect(intent, test_state)
        print(f"  door collapsed to: {new_state['object_states']['quantum_door']}")
        if event:
            print(f"  event: {event.event_type}, hint: {event.narrative_hint}")

    print("\nTEST 3: Entanglement cascade (take mirror_key)")
    test_state["current_room"] = "entanglement_lab"
    intent2 = parse_intent("take mirror key")
    print(f"  verb={intent2.verb}, object={intent2.object_id}")
    new_state2, _ = apply_quantum_effect(intent2, test_state)
    new_state2, cascade_events = check_entanglement_cascade("mirror_key", "take", new_state2)
    print(f"  mirror_key state: {new_state2['object_states']['mirror_key']}")
    print(f"  locked_mirror state: {new_state2['object_states']['locked_mirror']}")
    print(f"  cascade events: {[e.event_type for e in cascade_events]}")

    print("\nTEST 4: Observer gating (take quantum_key without prism_shard)")
    test_state["current_room"] = "observer_chamber"
    intent3 = parse_intent("take quantum key")
    val3 = is_valid_action(intent3, test_state)
    print(f"  valid={val3.is_valid}, reason={val3.reason[:60]}...")

    print("\nTEST 5: Observer gating (take quantum_key WITH prism_shard)")
    test_state["inventory"] = ["prism_shard"]
    test_state["object_states"]["quantum_key"] = "takeable"
    test_state["object_states"]["observer_entity"] = "distracted"
    val4 = is_valid_action(intent3, test_state)
    print(f"  valid={val4.is_valid}")

    print("\nTEST 6: Win condition check")
    win_state = {**test_state,
        "current_room": "core",
        "inventory": ["quantum_key"],
        "object_states": {**test_state["object_states"], "quantum_key": "held"}
    }
    win_intent = ActionIntent(verb="use", object_id="quantum_key", target_id="core_stabilizer")
    result = evaluate_win_loss(win_state, win_intent)
    print(f"  status={result.status}")

    print("\nTEST 7: Quantum state summary")
    summary = get_quantum_state_summary(test_state)
    print(json.dumps(summary, indent=2))

    print("\nAll tests passed.")
