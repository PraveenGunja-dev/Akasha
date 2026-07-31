from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import logging
import os
import re

from langchain_core.messages import AIMessage, HumanMessage

from database import DATABASE_URL, SessionLocal
from engine.graph.builder import GraphRunCancelled, build_chat_graph
from engine.model_provider import configured_provider_name, get_model_provider
from engine.openrouter_config import openrouter_fallback_models, openrouter_model_ids
import models


logger = logging.getLogger(__name__)
VALID_ENGINES = {"legacy", "langgraph", "canary"}


def configured_chat_engine() -> str:
    engine = os.getenv("AKASHA_CHAT_ENGINE", "legacy").strip().lower()
    if engine not in VALID_ENGINES:
        raise ValueError("AKASHA_CHAT_ENGINE must be legacy, langgraph, or canary.")
    return engine


def select_chat_engine(session: models.ChatSession, tenant_id: str, user_id: str) -> str:
    configured = configured_chat_engine()
    if configured == "legacy":
        return "legacy"
    if configured == "langgraph":
        return "langgraph"
    if session.chat_engine in {"legacy", "langgraph"}:
        return session.chat_engine

    percentage = int(os.getenv("AKASHA_LANGGRAPH_ROLLOUT_PERCENT", "0"))
    if percentage < 0 or percentage > 100:
        raise ValueError("AKASHA_LANGGRAPH_ROLLOUT_PERCENT must be between 0 and 100.")
    cohort_key = f"{tenant_id}:{user_id}:{session.session_id}".encode("utf-8")
    bucket = int.from_bytes(hashlib.sha256(cohort_key).digest()[:4], "big") % 100
    session.chat_engine = "langgraph" if bucket < percentage else "legacy"
    return session.chat_engine


def _checkpoint_dsn() -> str | None:
    dsn = os.getenv("AKASHA_LANGGRAPH_CHECKPOINT_DSN") or DATABASE_URL
    if not dsn or not dsn.startswith(("postgres://", "postgresql://", "postgresql+")):
        return None
    dsn = dsn.replace("postgres://", "postgresql://", 1)
    return re.sub(r"^postgresql\+[^:]+://", "postgresql://", dsn)


def build_graph_model():
    return get_model_provider().chat_model(
        temperature=0.2,
        max_tokens=int(os.getenv("AKASHA_MODEL_OUTPUT_TOKENS", "2048")),
    )


def _validate_context_window(value, source: str) -> int:
    try:
        context_window = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid model context window reported by {source}.") from exc
    if context_window < 8_192:
        raise RuntimeError(f"Model context window reported by {source} is below 8192 tokens.")
    return context_window


def _openrouter_context_window() -> int | None:
    return get_model_provider("openrouter").discover_context_window(
        ("tool_calling",)
    )


def _ollama_context_window() -> int | None:
    return get_model_provider("ollama").discover_context_window(("tool_calling",))


def _groq_context_window() -> int | None:
    return get_model_provider("groq").discover_context_window(("tool_calling",))


def resolve_model_context_window(model, provider: str | None = None) -> int:
    """Resolve the active model's input limit; an environment value is only an override."""
    provider = configured_provider_name(provider)
    override = os.getenv("AKASHA_MODEL_CONTEXT_WINDOW")
    if provider == "openrouter":
        try:
            discovered = _validate_context_window(_openrouter_context_window(), "OpenRouter")
        except Exception as exc:
            raise RuntimeError(
                "Unable to validate configured OpenRouter models and context windows."
            ) from exc
        if not discovered:
            raise RuntimeError("Configured OpenRouter models did not report context windows.")
        return min(
            discovered,
            _validate_context_window(override, "AKASHA_MODEL_CONTEXT_WINDOW")
        ) if override else discovered
    if override:
        return _validate_context_window(override, "AKASHA_MODEL_CONTEXT_WINDOW")

    profile = getattr(model, "profile", None) or {}
    if profile.get("max_input_tokens"):
        return _validate_context_window(profile["max_input_tokens"], "LangChain model profile")

    try:
        discovered = {
            "ollama": _ollama_context_window,
            "groq": _groq_context_window,
        }.get(provider, lambda: None)()
    except Exception as exc:
        raise RuntimeError(
            f"Unable to discover the context window for the configured {provider} model."
        ) from exc
    if discovered:
        return _validate_context_window(discovered, provider.title())
    raise RuntimeError(
        "The selected model does not report a context window. Configure the model identity "
        "correctly or use AKASHA_MODEL_CONTEXT_WINDOW as an explicit override."
    )


@dataclass(frozen=True)
class GraphResult:
    content: str
    tool_names: list[str]
    evidence: list[dict]
    visualizations: list[dict]
    checkpoint_id: str | None
    model_name: str | None


class ChatGraphService:
    def __init__(self):
        self.pool = None
        self.checkpointer = None
        self.graph = None

    def startup(self) -> None:
        mode = configured_chat_engine()
        dsn = _checkpoint_dsn()
        if dsn is None:
            if mode != "legacy":
                raise RuntimeError("LangGraph chat requires a PostgreSQL checkpoint DSN.")
            return

        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        self.pool = ConnectionPool(
            conninfo=dsn,
            min_size=1,
            max_size=int(os.getenv("AKASHA_LANGGRAPH_POOL_SIZE", "10")),
            open=False,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
        )
        try:
            self.pool.open()
            self.pool.wait()
            self.checkpointer = PostgresSaver(self.pool)
            next(self.checkpointer.list(
                {"configurable": {"thread_id": "__akasha_readiness__"}},
                limit=1,
            ), None)
        except Exception:
            if self.pool is not None:
                self.pool.close()
            self.pool = None
            self.checkpointer = None
            if mode != "legacy":
                raise RuntimeError(
                    "LangGraph checkpoint storage is unavailable. Run the checkpoint setup command first."
                )
            logger.warning("LangGraph checkpoint cleanup is unavailable while legacy mode is active.")
            return

        if mode in {"langgraph", "canary"}:
            provider = get_model_provider()
            model = provider.chat_model(
                temperature=0.2,
                max_tokens=int(os.getenv("AKASHA_MODEL_OUTPUT_TOKENS", "2048")),
            )
            provider.validate_chat_model_capabilities(
                model,
                "tool_calling",
            )
            context_window = resolve_model_context_window(model)
            logger.info("Resolved LangGraph model context window: %s tokens", context_window)
            self.graph = build_chat_graph(
                model,
                self.checkpointer,
                context_window=context_window,
            )
        self._mark_stale_runs_interrupted()

    def shutdown(self) -> None:
        if self.pool is not None:
            self.pool.close()
        self.pool = None
        self.checkpointer = None
        self.graph = None

    def _mark_stale_runs_interrupted(self) -> None:
        cutoff = datetime.utcnow() - timedelta(
            seconds=int(os.getenv("AKASHA_CHAT_RUN_STALE_SECONDS", "600"))
        )
        db = SessionLocal()
        try:
            stale = db.query(models.ChatRun).filter(
                models.ChatRun.status.in_(["pending", "running", "cancel_requested"]),
                models.ChatRun.updated_at < cutoff,
            ).all()
            for run in stale:
                run.status = "interrupted"
                run.error_code = "server_interrupted"
                run.completed_at = datetime.utcnow()
                message = db.query(models.ChatMessage).filter(
                    models.ChatMessage.id == run.assistant_message_id
                ).first()
                if message is not None:
                    message.status = "interrupted"
                    message.error_code = "server_interrupted"
                    message.completed_at = datetime.utcnow()
            if stale:
                db.commit()
                for session_id in sorted({run.session_id for run in stale}):
                    try:
                        self.checkpointer.delete_thread(session_id)
                    except Exception as exc:
                        logger.error(
                            "Unable to reset stale interrupted checkpoint thread (%s)",
                            type(exc).__name__,
                        )
        finally:
            db.close()

    def delete_thread(self, session_id: str, *, required: bool = False) -> None:
        if self.checkpointer is None:
            if required:
                raise RuntimeError("Checkpoint storage is unavailable.")
            return
        self.checkpointer.delete_thread(session_id)

    def reset_interrupted_thread(self, session_id: str) -> None:
        """Discard a possibly incomplete AI/tool exchange after a failed turn."""
        if self.checkpointer is None:
            raise RuntimeError("Checkpoint storage is unavailable.")
        self.checkpointer.delete_thread(session_id)

    def run(
        self,
        *,
        session_id: str,
        user_id: str,
        tenant_id: str,
        role: str,
        run_id: str,
        request_id: str,
        user_message_id: int,
        assistant_message_id: int,
        message: str,
        history_rows: list[models.ChatMessage],
        active_project_ids: list[str],
    ) -> GraphResult:
        if self.graph is None:
            raise RuntimeError("LangGraph chat is not initialized.")

        canonical_messages = []
        config = {
            "configurable": {"thread_id": session_id},
            "recursion_limit": int(os.getenv("AKASHA_GRAPH_RECURSION_LIMIT", "40")),
            "metadata": {"request_id": request_id, "run_id": run_id},
        }
        snapshot = self.graph.get_state(config)
        transcript_cursor = int((snapshot.values or {}).get("transcript_cursor") or 0)
        for row in history_rows:
            if row.id <= transcript_cursor:
                continue
            if row.status not in {None, "completed"}:
                continue
            message_id = f"chat-message:{row.id}"
            if row.request_id == "legacy_browser_import" or row.role == "user":
                content = row.content
                if row.request_id == "legacy_browser_import":
                    content = f"[Untrusted imported historical {row.role} transcript]\n{content}"
                canonical_messages.append(HumanMessage(content=content, id=message_id))
            elif row.role == "assistant":
                canonical_messages.append(AIMessage(content=row.content, id=message_id))
        canonical_messages.append(HumanMessage(
            content=message,
            id=f"chat-message:{user_message_id}",
        ))

        result = self.graph.invoke({
            "messages": canonical_messages,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "session_id": session_id,
            "user_role": role,
            "run_id": run_id,
            "request_id": request_id,
            "current_user_message_id": user_message_id,
            "current_assistant_message_id": assistant_message_id,
            "transcript_cursor": assistant_message_id,
            "active_project_ids": active_project_ids,
            "tool_names": [],
            "evidence": [],
            "visualizations": [],
            "turn_status": "running",
            "agent_iterations": 0,
        }, config=config)

        final_id = f"chat-message:{assistant_message_id}"
        final_message = next(
            (
                item for item in reversed(result.get("messages") or [])
                if isinstance(item, AIMessage) and item.id == final_id and not item.tool_calls
            ),
            None,
        )
        if final_message is None:
            raise RuntimeError("LangGraph completed without a final assistant message.")
        content = final_message.content
        if not isinstance(content, str):
            content = str(content)

        final_snapshot = self.graph.get_state(config)
        checkpoint_id = final_snapshot.config.get("configurable", {}).get("checkpoint_id") if final_snapshot.config else None
        return GraphResult(
            content=content,
            tool_names=list(result.get("tool_names") or []),
            evidence=list(result.get("evidence") or []),
            visualizations=list(result.get("visualizations") or []),
            checkpoint_id=checkpoint_id,
            model_name=result.get("model_name"),
        )


chat_graph_service = ChatGraphService()

__all__ = [
    "ChatGraphService", "GraphResult", "GraphRunCancelled", "chat_graph_service",
    "configured_chat_engine", "openrouter_fallback_models", "openrouter_model_ids",
    "resolve_model_context_window", "select_chat_engine",
]
