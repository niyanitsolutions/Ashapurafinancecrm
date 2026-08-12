"""The Event Engine: a minimal in-process publish/subscribe dispatcher for cross-cutting
side effects (decision 005 — "lead assigned -> notify -> remind -> log" style fan-out,
kept decoupled from whatever publishes the event).

First given real substance by Module 6C (every prior module's status handling was
deliberately kept trivial so this would be the first non-trivial state machine — see
docs/decisions/DECISIONS.md). No handlers are registered by default: Module 6C publishes
`workflow.status_changed` after every transition, but Notification Management and the
Reminder Engine are both explicitly out of scope for 6C, so there is currently no
subscriber that turns a publish into an actual SMS/WhatsApp/email/reminder — this is a
forward-compatible hook a future module can subscribe to without touching 6C's code, not
a working delivery path yet.

Deliberately NOT persisted (no collection of its own) and NOT a task queue — handlers run
in-process, in the same request, synchronously awaited in registration order. If a future
module needs at-least-once delivery or retries, it should have its *handler* enqueue an
Arq job (`app/worker/`), not change this dispatcher.
"""

from collections.abc import Awaitable, Callable
from typing import Any

Handler = Callable[[dict[str, Any]], Awaitable[None]]

_subscribers: dict[str, list[Handler]] = {}


def subscribe(event_key: str, handler: Handler) -> None:
    _subscribers.setdefault(event_key, []).append(handler)


async def publish(event_key: str, payload: dict[str, Any]) -> None:
    for handler in _subscribers.get(event_key, []):
        await handler(payload)


def clear_subscribers() -> None:
    """Test-only: reset all registered handlers between test cases."""
    _subscribers.clear()
