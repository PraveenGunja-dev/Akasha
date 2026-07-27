"""Small, payload-safe observability helpers for the active chat path."""

import hashlib
import json
import logging
from pathlib import Path
import traceback
import uuid


def resolve_request_id(_incoming_request_id: str | None = None) -> str:
    """Generate the operational correlation ID; caller IDs are intentionally ignored."""
    return str(uuid.uuid4())


def _hash_log_identifier(identifier: str | None) -> str | None:
    """Return a stable pseudonym without placing caller-controlled text in logs."""
    if identifier is None:
        return None
    if not isinstance(identifier, str):
        identifier = type(identifier).__name__
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _safe_log_request_id(request_id: str | None) -> str | None:
    if isinstance(request_id, str):
        try:
            return str(uuid.UUID(request_id))
        except ValueError:
            pass
    return _hash_log_identifier(request_id)


def serialize_sse_event(event_type: str, request_id: str, **payload) -> str:
    """Serialize one SSE data frame with a correlation ID."""
    event = {"type": event_type, **payload, "request_id": request_id}
    return f"data: {json.dumps(event, default=str)}\n\n"


def safe_exception_trace(exc: BaseException, max_frames: int = 8) -> list[dict]:
    """Return code locations for an exception chain without messages or local values."""
    chain = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        frames = traceback.extract_tb(current.__traceback__)[-max_frames:]
        chain.append({
            "error_type": type(current).__name__,
            "frames": [
                {
                    "file": Path(frame.filename).name,
                    "function": frame.name,
                    "line": frame.lineno,
                }
                for frame in frames
            ],
        })
        current = current.__cause__ or current.__context__
    return chain


def log_observability_event(
    logger: logging.Logger,
    event: str,
    *,
    request_id: str | None,
    session_id: str | None,
    elapsed_ms: int,
    response_intent: str,
    tool_names: list[str] | set[str] | tuple[str, ...],
    level: int = logging.INFO,
    **fields,
) -> None:
    """Write a JSON log record containing metadata only, never chat/tool payloads."""
    record = {
        "event": event,
        "request_id": _safe_log_request_id(request_id),
        "session_id": _hash_log_identifier(session_id),
        "elapsed_ms": elapsed_ms,
        "response_intent": response_intent,
        "tool_names": sorted(set(tool_names)),
        **fields,
    }
    logger.log(level, json.dumps(record, default=str, separators=(",", ":")))
