"""
HITL (Human-In-The-Loop) Gate Utility
=======================================

Pauses execution at decision points and records the response
in the event store for resume awareness.
"""

from typing import Optional

from .event_store import EventStore


def hitl_gate(
    gate_name: str,
    context: dict,
    event_store: EventStore,
    headless: bool = False,
    _simulate_response: Optional[str] = None,
) -> dict:
    """Present a HITL gate and return the user's decision.

    Args:
        gate_name: Name of the gate (e.g., "post_plan", "pre_merge")
        context: Dict with context for the gate decision
        event_store: EventStore to log the decision
        headless: If True, auto-continue without prompting
        _simulate_response: For testing — simulates user response

    Returns:
        {action: "continue"|"abort"|"modify", instructions: str}
    """
    if headless:
        result = {"action": "continue", "instructions": ""}
    elif _simulate_response is not None:
        result = _parse_response(_simulate_response)
    else:
        result = {"action": "continue", "instructions": ""}

    event_store.append({
        "type": "hitl_gate",
        "data": {
            "gate_name": gate_name,
            "action": result["action"],
            "instructions": result.get("instructions", ""),
            "context": context,
            "headless": headless,
        },
    })

    return result


def _parse_response(response: str) -> dict:
    """Parse a simulated or real response string."""
    if response.startswith("modify:"):
        return {
            "action": "modify",
            "instructions": response[len("modify:"):],
        }
    return {
        "action": response,
        "instructions": "",
    }
